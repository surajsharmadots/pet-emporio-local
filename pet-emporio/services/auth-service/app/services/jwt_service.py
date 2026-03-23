import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from pe_common.exceptions import UnauthorizedError
from pe_common.logging import get_logger

from ..config import settings

logger = get_logger(__name__)


def _private_key():
    # Settings (env var / monkeypatched in tests) take priority over file
    key_content = settings.JWT_PRIVATE_KEY.replace("\\n", "\n")
    if key_content.strip():
        if (key_content.startswith("-----BEGIN PRIVATE KEY-----")
                or key_content.startswith("-----BEGIN RSA PRIVATE KEY-----")):
            return key_content
        return f"-----BEGIN PRIVATE KEY-----\n{key_content}\n-----END PRIVATE KEY-----"
    # Fallback: read from file (local dev convenience)
    private_key_file = Path(__file__).parent.parent.parent / "private.pem"
    if private_key_file.exists():
        return private_key_file.read_text()
    raise RuntimeError("JWT_PRIVATE_KEY not set and private.pem not found")


def _public_key():
    # Settings (env var / monkeypatched in tests) take priority over file
    key_content = settings.JWT_PUBLIC_KEY.replace("\\n", "\n")
    if key_content.strip():
        if key_content.startswith("-----BEGIN PUBLIC KEY-----"):
            return key_content
        return f"-----BEGIN PUBLIC KEY-----\n{key_content}\n-----END PUBLIC KEY-----"
    # Fallback: read from file (local dev convenience)
    public_key_file = Path(__file__).parent.parent.parent / "public.pem"
    if public_key_file.exists():
        return public_key_file.read_text()
    raise RuntimeError("JWT_PUBLIC_KEY not set and public.pem not found")


def create_access_token(
    user_id: str,
    roles: list[str],
    session_id: str,
    tenant_id: str = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "pet-emporio",
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "session_id": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    
    try:
        private_key = _private_key()
        logger.info("jwt_key_debug", key_start=private_key[:50], key_length=len(private_key))
        return jwt.encode(payload, private_key, algorithm=settings.JWT_ALGORITHM)
    except Exception as e:
        logger.error("jwt_encode_error", error=str(e), algorithm=settings.JWT_ALGORITHM)
        raise


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