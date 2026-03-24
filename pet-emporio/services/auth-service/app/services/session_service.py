import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..repositories.auth import SessionRepository
from ..models.auth import Session
from . import jwt_service


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(
    db: AsyncSession,
    user_id: str,
    tenant_id: str = None,
    device_info: str = None,
    ip_address: str = None,
    remember_me: bool = False,
) -> tuple[str, str, Session]:
    """Creates session, returns (access_token, refresh_token, session).

    remember_me=True extends refresh token TTL from 30 days to 90 days
    (covers Doctor, Lab, Seller, Pharmacy, Groomer 'Save/remember login').
    """
    repo = SessionRepository(db)

    # Placeholder roles — in production these come from user-service
    roles = ["customer"]
    refresh_token = jwt_service.create_refresh_token()
    ttl_days = settings.REFRESH_TOKEN_EXPIRE_DAYS * 3 if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)

    session = await repo.create(
        user_id=user_id,
        refresh_token_hash=_hash_token(refresh_token),
        expires_at=expires_at,
        tenant_id=tenant_id,
        device_info=device_info,
        ip_address=ip_address,
    )

    access_token = jwt_service.create_access_token(
        user_id=user_id,
        roles=roles,
        session_id=session.id,
        tenant_id=tenant_id,
    )

    return access_token, refresh_token, session.id


async def refresh_session(
    db: AsyncSession,
    refresh_token: str,
    session_id: str,
) -> tuple[str, str] | None:
    """
    Validate refresh token, revoke old session, create new tokens.
    Returns (new_access_token, new_refresh_token) or None if invalid.
    """
    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)

    if not session:
        return None

    if session.revoked_at is not None:
        return None

    # Support tz-naive datetimes stored by SQLite in tests
    expires_at = session.expires_at
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if now > expires_at:
        return None

    if _hash_token(refresh_token) != session.refresh_token_hash:
        return None
    # Revoke old session and create a new one
    await repo.revoke(session_id)
    access_token, new_refresh_token, new_session = await create_session(
        db,
        user_id=session.user_id,
        tenant_id=session.tenant_id,
        device_info=session.device_info,
        ip_address=session.ip_address,
    )
    return access_token, new_refresh_token