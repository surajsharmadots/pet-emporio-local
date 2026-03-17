from fastapi import APIRouter
from pe_common.schemas import success_response
from ..schemas.auth import InternalVerifyRequest, InternalVerifyResponse
from ..services import jwt_service
from ..config import settings

router = APIRouter(prefix="/internal/v1/auth", tags=["internal"])


@router.post("/verify")
async def verify_token(body: InternalVerifyRequest):
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
    return success_response({"public_key": settings.JWT_PUBLIC_KEY})