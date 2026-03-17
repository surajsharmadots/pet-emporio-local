import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pe_common.exceptions import UnauthorizedError
from pe_common.logging import get_logger

from ..config import settings

logger = get_logger(__name__)


def _private_key():
    return settings.JWT_PRIVATE_KEY.replace("\\n", "\n")


def _public_key():
    return settings.JWT_PUBLIC_KEY.replace("\\n", "\n")


def create_access_token(
    user_id: str,
    roles: list[str],
    session_id: str,
    tenant_id: str = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "session_id": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _private_key(), algorithm=settings.JWT_ALGORITHM)


def create_refresh_token() -> str:
    return str(uuid.uuid4())


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, _public_key(), algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token expired")
    except jwt.InvalidTokenError as e:
        raise UnauthorizedError(f"Invalid token: {e}")


def decode_access_token_safe(token: str) -> dict | None:
    """Returns payload or None — never raises."""
    try:
        return jwt.decode(token, _public_key(), algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return {"_expired": True}
    except jwt.InvalidTokenError:
        return None