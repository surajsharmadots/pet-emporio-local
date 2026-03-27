"""
Facebook OAuth2 token verification.
Client sends `access_token` obtained from Facebook Login SDK.
We verify it server-side via the Facebook Graph API.
"""
import httpx
from pe_common.exceptions import AppException
from pe_common.logging import get_logger

logger = get_logger(__name__)

FACEBOOK_GRAPH_URL = "https://graph.facebook.com/me"


async def verify_facebook_token(access_token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                FACEBOOK_GRAPH_URL,
                params={
                    "fields": "id,name,email",
                    "access_token": access_token,
                },
            )
    except Exception as e:
        logger.warning("facebook_graph_api_error", error=str(e))
        raise AppException(
            code="SOCIAL_AUTH_ERROR",
            message="Could not reach Facebook Graph API",
            status_code=502,
        )

    if response.status_code != 200:
        raise AppException(
            code="INVALID_SOCIAL_TOKEN",
            message="Invalid or expired Facebook access token",
            status_code=401,
        )

    data = response.json()
    if "error" in data or "id" not in data:
        raise AppException(
            code="INVALID_SOCIAL_TOKEN",
            message="Invalid Facebook token response",
            status_code=401,
        )

    return {
        "provider_user_id": data["id"],
        "email": data.get("email"),
        "name": data.get("name"),
    }