from fastapi import APIRouter, Depends
from pydantic import BaseModel
import redis.asyncio as aioredis

from pe_common.schemas import success_response
from pe_common.exceptions import AppException
from pathlib import Path
from ..schemas.auth import InternalVerifyRequest, InternalVerifyResponse
from ..services import jwt_service, otp_service
from ..redis_client import get_redis
from ..config import settings

router = APIRouter(prefix="/internal/v1/auth", tags=["internal"])


@router.post("/verify")
async def verify_token(body: InternalVerifyRequest):
    # NOTE: this endpoint only verifies self-signed RS256 tokens (public.pem).
    # When KEYCLOAK_ENABLED=True, tokens are signed by Keycloak and cannot be
    # verified here. In production, Kong validates the token and injects
    # X-User-Id / X-User-Roles headers — downstream services never call this
    # endpoint. Use it only in local dev with KEYCLOAK_ENABLED=False.
    result = jwt_service.decode_access_token_safe(body.token)

    if result is None:
        return success_response(InternalVerifyResponse(valid=False, error="Invalid token").model_dump())

    if result.get("_expired"):
        return success_response(InternalVerifyResponse(valid=False, error="Token expired").model_dump())

    return success_response(InternalVerifyResponse(
        valid=True,
        user_id=result.get("sub"),
        tenant_id=result.get("tenant_id"),
        roles=result.get("roles", []),
        session_id=result.get("session_id"),
    ).model_dump())


@router.get("/public-key")
async def get_public_key():
    public_key_file = Path(__file__).parent.parent.parent / "public.pem"
    return success_response({"public_key": public_key_file.read_text()})


class OtpValidateRequest(BaseModel):
    mobile: str
    otp: str


@router.post("/otp/validate")
async def validate_otp_internal(
    body: OtpValidateRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Internal endpoint called by user-service during provider onboarding.
    Validates and consumes the OTP without issuing a session token.
    Returns 200 on success or 400 on failure.
    """
    result = await otp_service.verify_otp(redis, body.mobile, body.otp)

    if result == "expired":
        raise AppException(code="OTP_EXPIRED", message="OTP has expired.", status_code=400)
    if result in ("invalid", "too_many_attempts"):
        raise AppException(code="OTP_INVALID", message="Invalid OTP.", status_code=400)

    return success_response({"valid": True})