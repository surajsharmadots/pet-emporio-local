"""
Google Sign-In token verification.

Flow: Client sends the `id_token` received from Google Sign-In SDK.
We verify it against Google's public keys via their tokeninfo endpoint.
No server-side OAuth redirect needed for mobile/SPA clients.
"""

import httpx
from pe_common.exceptions import AppException
from pe_common.logging import get_logger

logger = get_logger(__name__)

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


async def verify_google_token(id_token: str, client_id: str | None = None) -> dict:
    """
    Verify a Google ID token and return user info.
    Returns dict with: provider_user_id, email, name
    Raises AppException on invalid token.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                GOOGLE_TOKENINFO_URL,
                params={"id_token": id_token},
            )
            data = response.json()
    except Exception as e:
        logger.error("google_tokeninfo_request_failed", error=str(e))
        raise AppException(
            code="SOCIAL_AUTH_FAILED",
            message="Could not verify Google token",
            status_code=502,
        )

    if response.status_code != 200 or "error_description" in data:
        logger.warning("google_token_invalid", detail=data.get("error_description"))
        raise AppException(
            code="INVALID_SOCIAL_TOKEN",
            message="Invalid Google ID token",
            status_code=401,
        )

    # Validate audience (aud) matches our client_id if configured
    if client_id and data.get("aud") != client_id:
        raise AppException(
            code="INVALID_SOCIAL_TOKEN",
            message="Google token audience mismatch",
            status_code=401,
        )

    return {
        "provider_user_id": data["sub"],
        "email": data.get("email"),
        "name": data.get("name") or data.get("given_name", ""),
    }
