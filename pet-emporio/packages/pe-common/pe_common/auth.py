import jwt
import os
from typing import Optional
from fastapi import Depends, Header
from .exceptions import UnauthorizedError
from fastapi import Request

try:
    from dotenv import load_dotenv, find_dotenv
    # find_dotenv walks up from cwd to find the nearest .env file
    _dotenv_path = find_dotenv(usecwd=True)
    if _dotenv_path:
        load_dotenv(_dotenv_path, override=False)
except ImportError:
    pass

# Verify tokens via Keycloak JWKS when KEYCLOAK_URL is set, otherwise fall back to static PUBLIC_KEY.

_KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "").rstrip("/")
_KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "pet-emporio")
_jwks_client = None

def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None and _KEYCLOAK_URL:
        try:
            from jwt import PyJWKClient
            jwks_uri = f"{_KEYCLOAK_URL}/realms/{_KEYCLOAK_REALM}/protocol/openid-connect/certs"
            _jwks_client = PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)
        except Exception:
            pass
    return _jwks_client

def _load_public_key(raw: str) -> str:
    """Accept either a full PEM string or a bare base64 key and return PEM."""
    raw = raw.strip()
    if not raw:
        return raw
    if raw.startswith("-----"):
        return raw
    return f"-----BEGIN PUBLIC KEY-----\n{raw}\n-----END PUBLIC KEY-----"

PUBLIC_KEY = _load_public_key(os.getenv("JWT_PUBLIC_KEY", ""))

def _normalise_payload(payload: dict) -> dict:
    """
    Normalise a decoded JWT payload into the standard pe_common shape:
        { user_id, roles, tenant_id, session_id, device_id }

    Handles two token formats:
      1. Keycloak OIDC token — `pe_user_id` custom claim (protocol mapper),
         flat `roles` array (realm-roles mapper), optional `tenant_id`/`device_id`.
         The `sub` field is the Keycloak-internal UUID, NOT the platform user_id.
      2. Legacy self-issued RS256 token — `sub` is the platform user_id,
         `roles` array present directly.
    """
    # Prefer pe_user_id (Keycloak custom claim) over sub (KC UUID or legacy user_id)
    user_id = payload.get("pe_user_id") or payload.get("sub", "")

    # Roles: flat array mapped by Keycloak protocol mapper, or legacy direct claim
    roles = payload.get("roles") or []

    return {
        "user_id": user_id,
        "roles": roles,
        "tenant_id": payload.get("tenant_id"),
        "session_id": payload.get("session_id") or payload.get("sid"),
        "device_id": payload.get("device_id"),
    }

def decode_jwt(token: str) -> dict:
    # Try JWKS (Keycloak dynamic key) first
    jwks_client = _get_jwks_client()
    if jwks_client:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            return _normalise_payload(payload)
        except jwt.ExpiredSignatureError:
            raise UnauthorizedError("Token expired")
        except jwt.InvalidTokenError:
            raise UnauthorizedError("Invalid token")
        except Exception:
            pass  # Keycloak unreachable — fall through to static key

    # Fallback: static public key (self-signed tokens from auth-service)
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
        return _normalise_payload(payload)
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
    # Read at request time so .env changes are picked up without restart
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
    if dev_mode and x_user_id:
        return {
            "user_id": x_user_id,
            "roles": x_user_roles.split(",") if x_user_roles else ["customer"],
            "tenant_id": x_tenant_id,
        }
    # In production: Kong injects X-User-Id, X-User-Roles, X-Tenant-Id headers
    if x_user_id:
        return {
            "user_id": x_user_id,
            "roles": x_user_roles.split(",") if x_user_roles else [],
            "tenant_id": x_tenant_id,
        }
    # In dev: fallback to JWT decode
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        return decode_jwt(token)
    raise UnauthorizedError()

def require_role(*roles: str):
    async def checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_roles = current_user.get("roles", [])
        if not any(role in user_roles for role in roles):
            from .exceptions import ForbiddenError
            raise ForbiddenError(f"Required role: {', '.join(roles)}")
        return current_user
    return checker
