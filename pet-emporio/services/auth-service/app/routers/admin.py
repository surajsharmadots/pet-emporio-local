"""
Admin router — exposes Keycloak admin operations as REST endpoints.

All endpoints require admin or sub_admin role.
These are consumed by the admin portal frontend and support tools.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.schemas import success_response
from pe_common.exceptions import AppException
from pe_common.auth import get_current_user, require_role

from ..config import settings
from ..services.keycloak_service import keycloak_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_admin_only = Depends(require_role("admin", "sub_admin"))


def _require_keycloak():
    if not settings.KEYCLOAK_ENABLED:
        raise AppException(
            code="KEYCLOAK_DISABLED",
            message="Keycloak is not enabled.",
            status_code=503,
        )


# Well-known / JWKS 

@router.get("/keycloak/well-known")
async def well_known():
    """
    GET /realms/pet-emporio/.well-known/openid-configuration
    Returns all Keycloak endpoint URLs and supported algorithms.
    Used by frontend and partner services to auto-discover endpoints.
    """
    _require_keycloak()
    data = await keycloak_service.get_well_known()
    return success_response(data)


@router.get("/keycloak/jwks")
async def jwks():
    """
    GET /realms/pet-emporio/protocol/openid-connect/certs
    Returns Keycloak's public signing keys in JWKS format.
    Any service can use this to verify JWTs without holding a static public key.
    """
    _require_keycloak()
    data = await keycloak_service.get_jwks()
    return success_response(data)


# User management

@router.get("/keycloak/users", dependencies=[_admin_only])
async def search_users(
    q: str = Query(default="", description="Search by name, email or mobile"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    GET /admin/realms/{realm}/users?search={q}
    Search and paginate Keycloak users. Used by admin portal user list.
    """
    _require_keycloak()
    users = await keycloak_service.search_users(query=q, offset=offset, limit=limit)
    count = await keycloak_service.get_user_count(query=q)
    return success_response({"users": users, "total": count})


@router.patch("/keycloak/users/{kc_user_id}/enable", dependencies=[_admin_only])
async def enable_user(kc_user_id: str):
    """
    PUT /admin/realms/{realm}/users/{id}  { enabled: true }
    Re-activate a disabled user account.
    """
    _require_keycloak()
    await keycloak_service.set_user_enabled(kc_user_id, enabled=True)
    return success_response({"message": "User enabled."})


@router.patch("/keycloak/users/{kc_user_id}/disable", dependencies=[_admin_only])
async def disable_user(kc_user_id: str):
    """
    PUT /admin/realms/{realm}/users/{id}  { enabled: false }
    Deactivate a user account without deleting it.
    """
    _require_keycloak()
    await keycloak_service.set_user_enabled(kc_user_id, enabled=False)
    return success_response({"message": "User disabled."})


# Session management 

@router.get("/keycloak/users/{kc_user_id}/sessions", dependencies=[_admin_only])
async def get_user_sessions(kc_user_id: str):
    """
    GET /admin/realms/{realm}/users/{id}/sessions
    List all active sessions for a user — includes IP, device, last activity.
    Used by admin portal and user's own "active devices" screen.
    """
    _require_keycloak()
    sessions = await keycloak_service.get_user_sessions(kc_user_id)
    return success_response(sessions)


@router.delete("/keycloak/sessions/{session_id}", dependencies=[_admin_only])
async def delete_session(session_id: str):
    """
    DELETE /admin/realms/{realm}/sessions/{sessionId}
    Revoke a specific session. Admin can kill a suspicious session
    without logging the user out everywhere.
    """
    _require_keycloak()
    await keycloak_service.delete_session(session_id)
    return success_response({"message": "Session revoked."})


# Audit events

@router.get("/keycloak/users/{kc_user_id}/events", dependencies=[_admin_only])
async def get_user_events(
    kc_user_id: str,
    event_type: str = Query(default=None, description="e.g. LOGIN, LOGIN_ERROR, LOGOUT"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    GET /admin/realms/{realm}/events?user={id}&type={type}
    Audit log of all login/logout/failure events for a user.
    Used by admin portal security tab and compliance reporting.
    """
    _require_keycloak()
    events = await keycloak_service.get_user_events(
        kc_user_id=kc_user_id,
        event_type=event_type,
        limit=limit,
    )
    return success_response(events)


# Attack detection

@router.get("/keycloak/users/{kc_user_id}/brute-force", dependencies=[_admin_only])
async def get_brute_force_status(kc_user_id: str):
    """
    GET /admin/realms/{realm}/attack-detection/brute-force/users/{id}
    Check if a user is locked out due to too many failed attempts.
    First thing support checks when a user says 'I can't log in'.
    """
    _require_keycloak()
    status = await keycloak_service.get_brute_force_status(kc_user_id)
    return success_response(status)


@router.delete("/keycloak/users/{kc_user_id}/brute-force", dependencies=[_admin_only])
async def clear_brute_force(kc_user_id: str):
    """
    DELETE /admin/realms/{realm}/attack-detection/brute-force/users/{id}
    Clear brute-force lockout — unblocks a user without resetting their account.
    """
    _require_keycloak()
    await keycloak_service.clear_brute_force(kc_user_id)
    return success_response({"message": "Brute-force lock cleared."})
