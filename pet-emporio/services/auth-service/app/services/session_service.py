"""
Session service — Keycloak-aware token lifecycle management.

Behaviour
─────────
When KEYCLOAK_ENABLED=True (production / staging):
  1. Sync the user into Keycloak (get_or_create_user) so the KC admin
     console always reflects real users and their roles.
  2. Issue the token pair via Keycloak token exchange — the returned
     access token is a proper OIDC JWT signed by Keycloak's realm key.
  3. Store a local Session row for device-info tracking and for the
     /sessions management endpoints; the refresh_token_hash records
     a SHA-256 of the KC refresh token so it can be validated on refresh.

When KEYCLOAK_ENABLED=False (early local dev, Keycloak not running):
  Falls back to the original self-issued RS256 JWT path.  This lets
  developers run only auth-service + Postgres without Keycloak.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.logging import get_logger

from ..config import settings
from ..repositories.auth import SessionRepository
from . import jwt_service

logger = get_logger(__name__)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(
    db: AsyncSession,
    user_id: str,
    roles: list[str] | None = None,
    tenant_id: str | None = None,
    device_id: str | None = None,
    device_info: str | None = None,
    ip_address: str | None = None,
    remember_me: bool = False,
    kc_user_id: str | None = None,
) -> tuple[str, str, str]:
    """
    Create a session and return (access_token, refresh_token, session_id).

    `roles` should be the real roles resolved from user-service/Keycloak.
    `kc_user_id` is the Keycloak internal UUID (stored for cross-referencing).
    `remember_me=True` triples the refresh TTL.
    """
    repo = SessionRepository(db)
    ttl_days = settings.REFRESH_TOKEN_EXPIRE_DAYS * 3 if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)

    if settings.KEYCLOAK_ENABLED and kc_user_id:
        # ── Keycloak path ──────────────────────────────────────────────────
        from .keycloak_service import keycloak_service

        try:
            kc_tokens = await keycloak_service.issue_token(
                kc_user_id=kc_user_id,
            )
            access_token = kc_tokens["access_token"]
            refresh_token = kc_tokens["refresh_token"]

        except Exception as exc:
            logger.warning(
                "keycloak_token_issue_failed_fallback",
                error=str(exc),
                user_id=user_id,
            )
            # Graceful fallback to self-issued token
            access_token, refresh_token = _create_local_tokens(
                user_id, roles or ["customer"], tenant_id
            )
    else:
        # ── Legacy / fallback path ─────────────────────────────────────────
        access_token, refresh_token = _create_local_tokens(
            user_id, roles or ["customer"], tenant_id
        )

    session = await repo.create(
        user_id=user_id,
        refresh_token_hash=_hash_token(refresh_token),
        expires_at=expires_at,
        tenant_id=tenant_id,
        device_id=device_id,
        device_info=device_info,
        ip_address=ip_address,
        kc_user_id=kc_user_id,
    )

    return access_token, refresh_token, session.id


def _create_local_tokens(
    user_id: str,
    roles: list[str],
    tenant_id: str | None,
) -> tuple[str, str]:
    """Issue self-signed RS256 JWT pair (fallback when Keycloak is unavailable)."""
    import uuid as _uuid
    refresh_token = str(_uuid.uuid4())
    access_token = jwt_service.create_access_token(
        user_id=user_id,
        roles=roles,
        session_id=str(_uuid.uuid4()),
        tenant_id=tenant_id,
    )
    return access_token, refresh_token


async def refresh_session(
    db: AsyncSession,
    refresh_token: str,
    session_id: str,
) -> tuple[str, str] | None:
    """
    Rotate tokens.

    Keycloak path  — delegates to KC's /token endpoint (proper OIDC rotation).
    Fallback path  — re-issues local JWT and new UUID refresh token.
    Returns (new_access_token, new_refresh_token) or None if invalid/expired.
    """
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)

    if not session or session.revoked_at is not None:
        return None

    expires_at = session.expires_at
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        return None

    if _hash_token(refresh_token) != session.refresh_token_hash:
        return None

    # Revoke the old session row immediately (rotation prevents replay)
    await repo.revoke(session_id)

    if settings.KEYCLOAK_ENABLED and session.kc_user_id:
        # ── Keycloak rotation ──────────────────────────────────────────────
        from .keycloak_service import keycloak_service
        try:
            kc_tokens = await keycloak_service.refresh_token(refresh_token)
            new_access = kc_tokens["access_token"]
            new_refresh = kc_tokens["refresh_token"]
        except Exception as exc:
            logger.warning("keycloak_refresh_failed_fallback", error=str(exc))
            # Known limitation: roles are not stored on the session row, so the
            # fallback token hardcodes ["customer"]. Non-customer users (admins,
            # doctors, etc.) will temporarily lose their elevated roles until KC
            # recovers and they log in again.
            new_access, new_refresh = _create_local_tokens(
                session.user_id, ["customer"], session.tenant_id
            )
    else:
        new_access, new_refresh = _create_local_tokens(
            session.user_id, ["customer"], session.tenant_id
        )

    ttl_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    new_expires = datetime.now(timezone.utc) + timedelta(days=ttl_days)

    await repo.create(
        user_id=session.user_id,
        refresh_token_hash=_hash_token(new_refresh),
        expires_at=new_expires,
        tenant_id=session.tenant_id,
        device_id=session.device_id,
        device_info=session.device_info,
        ip_address=session.ip_address,
        kc_user_id=session.kc_user_id,
    )

    return new_access, new_refresh
