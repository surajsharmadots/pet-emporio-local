from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from pe_common.schemas import success_response
from pe_common.exceptions import AppException

from ..database import get_db
from ..redis_client import get_redis
from ..schemas.auth import (
    OtpSendRequest, OtpSendResponse,
    OtpVerifyRequest, TokenPair,
    RefreshRequest, LogoutRequest, SessionInfo,
    MfaSetupResponse, MfaVerifyRequest,
)
from ..services import otp_service, session_service, jwt_service
from ..repositories.auth import SessionRepository, MfaRepository
from pe_common.auth import get_current_user
import pyotp

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/otp/send")
async def send_otp(
    body: OtpSendRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    allowed = await otp_service.check_rate_limit(redis, body.mobile)
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

    # Use mobile as user_id placeholder until user-service assigns a real ID
    user_id = body.mobile
    ip = request.client.host if request.client else None

    access_token, refresh_token, session = await session_service.create_session(
        db,
        user_id=user_id,
        device_info=body.device_info,
        ip_address=ip,
    )

    return success_response(TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=900,
    ).model_dump())


@router.post("/token/refresh")
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    # Decode without verification to extract session_id
    try:
        import jwt as pyjwt
        from ..config import settings
        unverified = pyjwt.decode(
            body.refresh_token,
            options={"verify_signature": False, "verify_exp": False},
        )
        session_id = unverified.get("session_id") or unverified.get("sub")
    except Exception:
        raise AppException(code="INVALID_TOKEN", message="Invalid refresh token", status_code=401)

    # refresh_token here is a UUID, not a JWT — get session_id from the payload
    # Since refresh tokens are UUIDs, we need session_id passed separately or embedded
    # For simplicity: the client sends {refresh_token, session_id}
    raise AppException(code="NOT_IMPLEMENTED", message="Use /token/refresh with session_id", status_code=400)


@router.post("/token/refresh/{session_id}")
async def refresh_token_with_session(
    session_id: str,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await session_service.refresh_session(db, body.refresh_token, session_id)
    if result is None:
        raise AppException(code="INVALID_TOKEN", message="Invalid or expired refresh token", status_code=401)

    access_token, new_refresh_token = result
    return success_response(TokenPair(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=900,
    ).model_dump())


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = SessionRepository(db)
    revoked = await repo.revoke(body.session_id)
    if not revoked:
        raise AppException(code="NOT_FOUND", message="Session not found", status_code=404)
    return success_response({"message": "Logged out successfully"})


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
        raise AppException(code="NOT_FOUND", message="Session not found", status_code=404)
    await repo.revoke(session_id)
    return success_response({"message": "Session revoked"})


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