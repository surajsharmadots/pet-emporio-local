"""
Apple Sign In identity_token verification.
Client sends the `identity_token` (JWT) obtained from Apple Sign In SDK.
We verify it server-side using Apple's public keys (JWKS endpoint).
"""
import httpx
import jwt as pyjwt
from jwt.algorithms import RSAAlgorithm
import json

from pe_common.exceptions import AppException
from pe_common.logging import get_logger

logger = get_logger(__name__)

APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"


async def _get_apple_public_keys() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(APPLE_KEYS_URL)
            response.raise_for_status()
            return response.json()["keys"]
    except Exception as e:
        logger.warning("apple_keys_fetch_error", error=str(e))
        raise AppException(
            code="SOCIAL_AUTH_ERROR",
            message="Could not fetch Apple public keys",
            status_code=502,
        )


async def verify_apple_token(identity_token: str, audience: str | None = None) -> dict:
    """
    Verify an Apple identity_token JWT and return user info.

    Args:
        identity_token: JWT string from Apple Sign In SDK.
        audience: Your app's bundle ID (e.g. "com.petemporio.app").
                  If None, audience check is skipped (dev mode).

    Returns:
        dict with keys: provider_user_id, email (optional)

    Raises:
        AppException 401 if token is invalid, expired, or issuer mismatch.
    """
    # Decode header to get kid (key ID)
    try:
        unverified_header = pyjwt.get_unverified_header(identity_token)
    except Exception:
        raise AppException(
            code="INVALID_SOCIAL_TOKEN",
            message="Malformed Apple identity token",
            status_code=401,
        )

    kid = unverified_header.get("kid")
    apple_keys = await _get_apple_public_keys()

    # Find the matching public key
    matching_key = next((k for k in apple_keys if k.get("kid") == kid), None)
    if not matching_key:
        raise AppException(
            code="INVALID_SOCIAL_TOKEN",
            message="Apple public key not found for token",
            status_code=401,
        )

    # Convert JWK to PEM
    try:
        public_key = RSAAlgorithm.from_jwk(json.dumps(matching_key))
    except Exception as e:
        logger.warning("apple_key_parse_error", error=str(e))
        raise AppException(
            code="SOCIAL_AUTH_ERROR",
            message="Failed to parse Apple public key",
            status_code=502,
        )

    # Verify the JWT
    try:
        options = {"verify_aud": audience is not None}
        payload = pyjwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=APPLE_ISSUER,
            options=options,
        )
    except pyjwt.ExpiredSignatureError:
        raise AppException(
            code="INVALID_SOCIAL_TOKEN",
            message="Apple identity token has expired",
            status_code=401,
        )
    except pyjwt.InvalidTokenError as e:
        raise AppException(
            code="INVALID_SOCIAL_TOKEN",
            message=f"Invalid Apple identity token: {e}",
            status_code=401,
        )

    return {
        "provider_user_id": payload["sub"],
        "email": payload.get("email"),
        "name": None,  # Apple doesn't include name in JWT; client sends it separately on first login
    }