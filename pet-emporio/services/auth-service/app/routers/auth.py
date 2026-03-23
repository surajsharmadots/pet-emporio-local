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
    FacebookAuthRequest, AppleAuthRequest,
)
from ..services import otp_service, session_service
from ..services.facebook_auth import verify_facebook_token
from ..services.apple_auth import verify_apple_token
from ..repositories.auth import SessionRepository, MfaRepository, SocialAccountRepository
import pyotp

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def _get_or_create_user(mobile: str) -> str:
    """
    Calls user-service internal API to get or create a user by mobile number.
    Returns the real user_id (UUID).

    Falls back to mobile number as user_id if user-service is not reachable
    (e.g. during early development before user-service is built).
    """
    user_service_url = getattr(settings, "USER_SERVICE_URL", "http://user-service:8000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{user_service_url}/internal/v1/users/get-or-create",
                json={"mobile": mobile},
            )
            if response.status_code == 200:
                return response.json()["data"]["user_id"]
    except Exception as e:
        logger.warning(
            "user_service_unreachable",
            detail="Falling back to mobile as user_id. Build user-service (PROMPT 4) to fix this.",
            error=str(e),
        )
    # Fallback: use mobile as user_id (dev only, before user-service exists)
    return mobile


# ─── OTP ──────────────────────────────────────────────────────────────────────

@router.post("/otp/send")
async def send_otp(
    body: OtpSendRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    print("checking rate limit...")
    allowed = await otp_service.check_rate_limit(redis, body.mobile)
    print("allowed:", allowed)
    if not allowed:
        raise AppException(
            code="RATE_LIMITED",
            message="Too many OTP requests. Try again in 10 minutes.",
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
        raise AppException(code="OTP_EXPIRED", message="OTP has expired", status_code=410)
    if result in ("invalid", "too_many_attempts"):
        raise AppException(code="OTP_INVALID", message="Invalid OTP", status_code=400)

    ip = request.client.host if request.client else None

    # Get or create user in user-service (returns real UUID or mobile as fallback)
    user_id = await _get_or_create_user(body.mobile)

    access_token, refresh_token, session_id = await session_service.create_session(
        db,
        user_id=user_id,
        device_info=body.device_info,
        ip_address=ip,
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
    Refresh access token using refresh_token + session_id.
    Client must store both values received from /otp/verify.
    """
    result = await session_service.refresh_session(db, body.refresh_token, session_id)

    if result is None:
        raise AppException(
            code="INVALID_TOKEN",
            message="Invalid or expired refresh token",
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
    # current_user: dict = Depends(get_current_user),
):
    repo = SessionRepository(db)
    revoked = await repo.revoke(body.session_id)
    if not revoked:
        raise AppException(code="NOT_FOUND", message="Session not found", status_code=404)
    return success_response({"message": "Logged out successfully"})


@router.get("/sessions")
async def list_sessions(
    request: Request,
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
    # current_user: dict = Depends(get_current_user),
):
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    # if not session or session.user_id != current_user["user_id"]:
    #     raise AppException(code="NOT_FOUND", message="Session not found", status_code=404)
    await repo.revoke(session_id)
    return success_response({"message": "Session revoked"})


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
        raise AppException(code="MFA_NOT_SETUP", message="MFA not configured", status_code=400)

    totp = pyotp.TOTP(config.totp_secret_encrypted)
    if not totp.verify(body.code):
        raise AppException(code="MFA_INVALID", message="Invalid TOTP code", status_code=400)

    await repo.enable(current_user["user_id"])
    return success_response({"message": "MFA enabled successfully"})

# ─── Social Login ─────────────────────────────────────────────────────────────

async def _social_login(
    db: AsyncSession,
    provider: str,
    provider_user_id: str,
    email: str | None,
    name: str | None,
    access_token: str | None,
    device_info: str | None,
    ip: str | None,
) -> tuple[str, str, str]:
    """
    Shared logic for all social login providers:
    1. Get or create user in user-service via internal API.
    2. Upsert social_accounts record.
    3. Create session and return (access_token, refresh_token, session_id).
    """
    user_service_url = getattr(settings, "USER_SERVICE_URL", "http://user-service:8000")
    user_id = provider_user_id  # fallback if user-service unreachable

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{user_service_url}/internal/v1/users/get-or-create",
                json={"mobile": None, "email": email, "provider": provider,
                      "provider_user_id": provider_user_id, "full_name": name or ""},
            )
            if resp.status_code == 200:
                user_id = resp.json()["data"]["user_id"]
    except Exception as e:
        logger.warning("user_service_unreachable_social", provider=provider, error=str(e))

    social_repo = SocialAccountRepository(db)
    await social_repo.upsert(user_id, provider, provider_user_id, access_token)

    at, rt, session_id = await session_service.create_session(
        db, user_id=user_id, device_info=device_info, ip_address=ip,
    )
    return at, rt, session_id


@router.post("/social/facebook")
async def social_facebook(
    body: FacebookAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Facebook OAuth2 — client sends access_token from Facebook Login SDK."""
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
        ip=ip,
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
    """Apple Sign In — client sends identity_token from Apple Sign In SDK."""
    audience = getattr(settings, "APPLE_BUNDLE_ID", None)
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
        ip=ip,
    )
    return success_response(TokenPair(
        access_token=at,
        refresh_token=rt,
        session_id=session_id,
        token_type="bearer",
        expires_in=900,
    ).model_dump())
