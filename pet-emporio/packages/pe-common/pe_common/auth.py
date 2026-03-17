import jwt
import os
from typing import Optional
from fastapi import Depends, Header
from .exceptions import UnauthorizedError

PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY", "")


def decode_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid token")


async def get_current_user(
    x_user_id: Optional[str] = Header(None),
    x_user_roles: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
) -> dict:
    # In production: Kong injects X-User-Id, X-User-Roles, X-Tenant-Id headers
    if x_user_id:
        return {
            "user_id": x_user_id,
            "roles": x_user_roles.split(",") if x_user_roles else [],
            "tenant_id": x_tenant_id
        }
    # In dev: fallback to JWT decode
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        return decode_jwt(token)
    raise UnauthorizedError()


async def require_role(*roles: str):
    async def checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_roles = current_user.get("roles", [])
        if not any(role in user_roles for role in roles):
            from .exceptions import ForbiddenError
            raise ForbiddenError(f"Required role: {', '.join(roles)}")
        return current_user
    return checker