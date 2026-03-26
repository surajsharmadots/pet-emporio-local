from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
import httpx

from pe_common.schemas import success_response
from pe_common.exceptions import AppException
from pe_common.logging import get_logger
from pe_common.auth import get_current_user

from ..database import get_db
from ..redis_client import get_redis
from ..config import settings
from ..schemas.auth import (
    OtpSendRequest, OtpSendResponse,
    OtpVerifyRequest, TokenPair,
    RefreshRequest, LogoutRequest, SessionInfo,
    MfaSetupResponse, MfaVerifyRequest,
    GoogleAuthRequest, FacebookAuthRequest, AppleAuthRequest,
    DeviceInfo,
)
from ..services import otp_service, session_service
from ..services import device_service
from ..services.google_auth import verify_google_token
from ..services.facebook_auth import verify_facebook_token
from ..services.apple_auth import verify_apple_token
from ..repositories.auth import SessionRepository, MfaRepository, SocialAccountRepository
import pyotp

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _get_or_create_user(mobile: str) -> str:
    """
    Calls user-service to get or create a user record by mobile number.
    Returns the user_id (UUID string).
    Falls back to the mobile number itself when user-service is unreachable,
    which only happens in early local development before user-service is running.
    """
    user_service_url = settings.USER_SERVICE_URL
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{user_service_url}/internal/v1/users/get-or-create",
                json={"mobile": mobile},
            )
            if response.status_code == 200:
                return response.json()["data"]["user_id"]
    except Exception as e:
        logger.warning("user_service_unreachable", error=str(e))
    return mobile


async def _check_account_status(mobile: str) -> dict:
    """
    Checks user-service for the account status of a given mobile number.
    Returns a dict with keys: exists, is_active, user_type.

    Provider accounts (doctor, seller, lab, pharmacy, groomer) must be
    approved by an admin (is_active=True) before they can log in.
    Customer and admin accounts are active immediately after creation.
    """
    user_service_url = getattr(settings, "USER_SERVICE_URL", "http://user-service:8000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{user_service_url}/internal/v1/users/status-by-mobile/{mobile}",
            )
            if response.status_code == 200:
                return response.json()["data"]
            if response.status_code == 404:
                return {"exists": False}
    except Exception as e:
        logger.warning("user_service_status_check_failed", error=str(e))
    return {"exists": True, "is_active": True, "user_type": "customer"}


async def _get_user_roles(user_id: str) -> list[str]:
    """
    Fetch the roles assigned to a user from user-service.
    Returns ["customer"] as a safe default if unreachable.
    """
    user_service_url = getattr(settings, "USER_SERVICE_URL", "http://user-service:8000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{user_service_url}/internal/v1/users/{user_id}/roles",
            )
            if response.status_code == 200:
                return response.json()["data"]["roles"]
    except Exception as e:
        logger.warning("user_service_roles_fetch_failed", user_id=user_id, error=str(e))
    return ["customer"]


async def _sync_to_keycloak(
    user_id: str,
    mobile: str | None,
    email: str | None,
    name: str | None,
    roles: list[str],
    tenant_id: str | None,
) -> str | None:
    """
    Sync the platform user into Keycloak and return the kc_user_id.
    Returns None if Keycloak is disabled or the sync fails gracefully.
    """
    if not settings.KEYCLOAK_ENABLED:
        return None
    try:
        from ..services.keycloak_service import keycloak_service
        kc_user_id = await keycloak_service.get_or_create_user(
            platform_user_id=user_id,
            mobile=mobile,
            email=email,
            full_name=name,
            roles=roles,
            tenant_id=tenant_id,
        )
        return kc_user_id
    except Exception as exc:
        logger.warning(
            "keycloak_sync_failed",
            user_id=user_id,
            error=str(exc),
            exc_type=type(exc).__name__,
        )
        return None


_PROVIDER_TYPES = {"doctor", "seller", "lab_technician", "groomer", "pharmacist"}


async def _social_login(
    db: AsyncSession,
    provider: str,
    provider_user_id: str,
    email: str | None,
    name: str | None,
    access_token: str | None,
    device_info: str | None,
    device_id: str | None,
    device_fingerprint: str | None,
    ip: str | None,
    user_agent: str | None,
    remember_me: bool = False,
) -> tuple[str, str, str]:
    """
    Shared logic for all social login providers.
    Steps:
      1. Get or create the user record in user-service.
      2. Upsert the social_accounts record (links provider ID to user).
      3. Register / validate the device.
      4. Sync user into Keycloak (if enabled).
      5. Create a session and return (access_token, refresh_token, session_id).
    """
    user_service_url = getattr(settings, "USER_SERVICE_URL", "http://user-service:8000")
    user_id = provider_user_id  # fallback if user-service is unreachable

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{user_service_url}/internal/v1/users/get-or-create",
                json={
                    "mobile": None,
                    "email": email,
                    "provider": provider,
                    "provider_user_id": provider_user_id,
                    "full_name": name or "",
                },
            )
            if resp.status_code == 200:
                user_id = resp.json()["data"]["user_id"]
    except Exception as e:
        logger.warning("user_service_unreachable_social", provider=provider, error=str(e))

    social_repo = SocialAccountRepository(db)
    await social_repo.upsert(user_id, provider, provider_user_id, access_token)

    # Device binding
    resolved_device_id = await device_service.register_or_validate_device(
        db,
        user_id=user_id,
        device_id=device_id,
        device_fingerprint=device_fingerprint,
        ip_address=ip,
        user_agent=user_agent,
    )

    # Fetch roles and sync to Keycloak
    roles = await _get_user_roles(user_id)
    kc_user_id = await _sync_to_keycloak(
        user_id=user_id,
        mobile=None,
        email=email,
        name=name,
        roles=roles,
        tenant_id=None,
    )

    at, rt, session_id = await session_service.create_session(
        db,
        user_id=user_id,
        roles=roles,
        device_id=resolved_device_id,
        device_info=device_info,
        ip_address=ip,
        remember_me=remember_me,
        kc_user_id=kc_user_id,
    )
    return at, rt, session_id


# ─── OTP ──────────────────────────────────────────────────────────────────────

@router.post("/otp/send")
async def send_otp(
    body: OtpSendRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    allowed = await otp_service.check_rate_limit(redis, body.mobile)
    if not allowed:
        raise AppException(
            code="RATE_LIMITED",
            message="Too many OTP requests. Please try again in 10 minutes.",
            status_code=429,
        )
    await otp_service.send_otp(redis, body.mobile)
    return success_response(OtpSendResponse().model_dump())


@router.post("/otp/verify")
async def verify_otp(
    body: OtpVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    result = await otp_service.verify_otp(redis, body.mobile, body.otp)

    if result == "expired":
        raise AppException(code="OTP_EXPIRED", message="OTP has expired.", status_code=410)
    if result in ("invalid", "too_many_attempts"):
        raise AppException(code="OTP_INVALID", message="Invalid OTP.", status_code=400)

    # Check account status before issuing a token.
    #
    # Three scenarios:
    #   1. Account does not exist + portal is "customer" (or unset)
    #      → Normal customer self-registration. get-or-create will create the account.
    #
    #   2. Account does not exist + portal is a provider type
    #      → Provider tried to log in without submitting an onboarding form first.
    #        Block them — they must go through /provider/onboard.
    #
    #   3. Account exists but is_active=False
    #      → Provider account is pending admin approval, or was deactivated.
    status = await _check_account_status(body.mobile)
    portal = (body.portal or "customer").lower()

    if not status.get("exists", True):
        if portal in _PROVIDER_TYPES:
            raise AppException(
                code="ACCOUNT_NOT_FOUND",
                message="No account found for this mobile number. Please register via the onboarding form first.",
                status_code=404,
            )
        # Customer self-registration — account will be created by get-or-create below.
    elif not status.get("is_active", True):
        user_type = status.get("user_type", "")
        if user_type in _PROVIDER_TYPES:
            raise AppException(
                code="ACCOUNT_PENDING_APPROVAL",
                message="Your account is pending admin approval. You will be notified once approved.",
                status_code=403,
            )
        raise AppException(
            code="ACCOUNT_INACTIVE",
            message="Your account has been deactivated. Please contact support.",
            status_code=403,
        )

    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    user_id = await _get_or_create_user(body.mobile)

    # Device binding — register new device or validate returning one
    resolved_device_id = await device_service.register_or_validate_device(
        db,
        user_id=user_id,
        device_id=body.device_id,
        device_fingerprint=body.device_fingerprint,
        ip_address=ip,
        user_agent=user_agent,
    )

    # Fetch real roles from user-service
    roles = await _get_user_roles(user_id)

    # Sync user into Keycloak (creates/updates KC user record + assigns roles)
    kc_user_id = await _sync_to_keycloak(
        user_id=user_id,
        mobile=body.mobile,
        email=None,
        name=None,
        roles=roles,
        tenant_id=None,
    )

    access_token, refresh_token, session_id = await session_service.create_session(
        db,
        user_id=user_id,
        roles=roles,
        device_id=resolved_device_id,
        device_info=body.device_info,
        ip_address=ip,
        remember_me=body.remember_me,
        kc_user_id=kc_user_id,
    )

    return success_response(TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        session_id=session_id,
        token_type="bearer",
        expires_in=900,
    ).model_dump())


# ─── Token ────────────────────────────────────────────────────────────────────

@router.post("/token/refresh/{session_id}")
async def refresh_token(
    session_id: str,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    The old session is revoked immediately to enforce token rotation.
    """
    result = await session_service.refresh_session(db, body.refresh_token, session_id)

    if result is None:
        raise AppException(
            code="INVALID_TOKEN",
            message="Refresh token is invalid or has expired.",
            status_code=401,
        )

    access_token, new_refresh_token = result
    return success_response(TokenPair(
        access_token=access_token,
        refresh_token=new_refresh_token,
        session_id=session_id,
        token_type="bearer",
        expires_in=900,
    ).model_dump())


# ─── Session ──────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = SessionRepository(db)
    session = await repo.get_by_id(body.session_id)
    if not session:
        raise AppException(code="NOT_FOUND", message="Session not found.", status_code=404)

    await repo.revoke(body.session_id)

    # Also revoke in Keycloak if this was a KC-issued session
    if settings.KEYCLOAK_ENABLED and session.kc_user_id:
        try:
            from ..services.keycloak_service import keycloak_service
            await keycloak_service.logout_all_sessions(session.kc_user_id)
        except Exception as exc:
            logger.warning("keycloak_logout_failed", error=str(exc))

    return success_response({"message": "Logged out successfully."})


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = SessionRepository(db)
    sessions = await repo.get_active_by_user(current_user["user_id"])
    return success_response([
        SessionInfo(
            id=s.id,
            device_info=s.device_info,
            ip_address=s.ip_address,
            created_at=s.created_at,
            expires_at=s.expires_at,
        ).model_dump()
        for s in sessions
    ])


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.user_id != current_user["user_id"]:
        raise AppException(code="NOT_FOUND", message="Session not found.", status_code=404)
    await repo.revoke(session_id)
    return success_response({"message": "Session revoked."})


# ─── Devices ──────────────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all registered devices for the current user."""
    devices = await device_service.list_devices(db, current_user["user_id"])
    return success_response([
        DeviceInfo(
            device_id=d.device_id,
            user_agent=d.user_agent,
            ip_address=d.ip_address,
            created_at=d.created_at,
            last_seen_at=d.last_seen_at,
        ).model_dump()
        for d in devices
    ])


@router.delete("/devices/{device_id}")
async def revoke_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Revoke a registered device. Active sessions on this device remain valid until expiry."""
    removed = await device_service.revoke_device(db, current_user["user_id"], device_id)
    if not removed:
        raise AppException(code="NOT_FOUND", message="Device not found.", status_code=404)
    return success_response({"message": "Device revoked."})


# ─── MFA ──────────────────────────────────────────────────────────────────────

@router.post("/mfa/setup")
async def setup_mfa(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    secret = pyotp.random_base32()
    repo = MfaRepository(db)
    await repo.upsert(user_id, secret)
    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(name=user_id, issuer_name="Pet Emporio")
    return success_response(MfaSetupResponse(secret=secret, qr_uri=qr_uri).model_dump())


@router.post("/mfa/verify")
async def verify_mfa(
    body: MfaVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = MfaRepository(db)
    config = await repo.get_by_user(current_user["user_id"])
    if not config:
        raise AppException(code="MFA_NOT_SETUP", message="MFA is not configured for this account.", status_code=400)

    totp = pyotp.TOTP(config.totp_secret_encrypted)
    if not totp.verify(body.code):
        raise AppException(code="MFA_INVALID", message="Invalid TOTP code.", status_code=400)

    await repo.enable(current_user["user_id"])
    return success_response({"message": "MFA enabled successfully."})


# ─── Social Login ─────────────────────────────────────────────────────────────

@router.post("/social/google")
async def social_google(
    body: GoogleAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Google Sign-In for the customer portal.
    The client sends the ID token received from the Google Sign-In SDK.
    We verify it against Google's public keys and create/fetch the user record.
    """
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", None) or None
    info = await verify_google_token(body.id_token, client_id=client_id)
    ip = request.client.host if request.client else None
    at, rt, session_id = await _social_login(
        db,
        provider="google",
        provider_user_id=info["provider_user_id"],
        email=info.get("email"),
        name=info.get("name"),
        access_token=None,
        device_info=body.device_info,
        device_id=body.device_id,
        device_fingerprint=body.device_fingerprint,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        remember_me=body.remember_me,
    )
    return success_response(TokenPair(
        access_token=at,
        refresh_token=rt,
        session_id=session_id,
        token_type="bearer",
        expires_in=900,
    ).model_dump())


@router.post("/social/facebook")
async def social_facebook(
    body: FacebookAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Facebook Login for the customer portal.
    The client sends the access token received from the Facebook Login SDK.
    """
    info = await verify_facebook_token(body.access_token)
    ip = request.client.host if request.client else None
    at, rt, session_id = await _social_login(
        db,
        provider="facebook",
        provider_user_id=info["provider_user_id"],
        email=info.get("email"),
        name=info.get("name"),
        access_token=body.access_token,
        device_info=body.device_info,
        device_id=body.device_id,
        device_fingerprint=body.device_fingerprint,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        remember_me=body.remember_me,
    )
    return success_response(TokenPair(
        access_token=at,
        refresh_token=rt,
        session_id=session_id,
        token_type="bearer",
        expires_in=900,
    ).model_dump())


@router.post("/social/apple")
async def social_apple(
    body: AppleAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Apple Sign In for the customer portal.
    The client sends the identity token received from the Apple Sign In SDK.
    """
    audience = getattr(settings, "APPLE_BUNDLE_ID", None) or None
    info = await verify_apple_token(body.identity_token, audience=audience)
    ip = request.client.host if request.client else None
    at, rt, session_id = await _social_login(
        db,
        provider="apple",
        provider_user_id=info["provider_user_id"],
        email=info.get("email"),
        name=info.get("name"),
        access_token=None,
        device_info=body.device_info,
        device_id=body.device_id,
        device_fingerprint=body.device_fingerprint,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        remember_me=body.remember_me,
    )
    return success_response(TokenPair(
        access_token=at,
        refresh_token=rt,
        session_id=session_id,
        token_type="bearer",
        expires_in=900,
    ).model_dump())
