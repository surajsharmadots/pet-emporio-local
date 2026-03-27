"""Device registration and fingerprint validation for mobile auth."""

from __future__ import annotations

import hashlib
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.logging import get_logger

from ..models.auth import DeviceRegistration
from ..repositories.auth import DeviceRepository

logger = get_logger(__name__)


def _fingerprint_hash(raw: str) -> str:
    """Normalise and hash a raw device fingerprint string."""
    return hashlib.sha256(raw.strip().lower().encode()).hexdigest()


async def register_or_validate_device(
    db: AsyncSession,
    user_id: str,
    device_id: Optional[str],
    device_fingerprint: Optional[str],
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """
    Idempotently register a device and return its `device_id`.

    - If `device_id` is None a new one is generated (first-ever login).
    - If `device_id` is provided but unknown, it is registered now.
    - If `device_id` is known but the fingerprint changed, the mismatch is
      logged and the device_id is still returned (risk signal, not a hard
      block — callers can escalate to MFA if desired).

    Returns the canonical device_id to embed in the session / JWT.
    """
    repo = DeviceRepository(db)

    # no device_id supplied → first login, generate one
    if not device_id:
        device_id = str(_uuid.uuid4())

    existing = await repo.get(device_id)

    fp_hash = _fingerprint_hash(device_fingerprint) if device_fingerprint else None

    if existing is None:
        await repo.create(
            device_id=device_id,
            user_id=user_id,
            fingerprint_hash=fp_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("device_registered", device_id=device_id, user_id=user_id)
    else:
        #  known device_id but fingerprint mismatch → log a warning (potential risk signal)
        if fp_hash and existing.fingerprint_hash and fp_hash != existing.fingerprint_hash:
            logger.warning(
                "device_fingerprint_mismatch",
                device_id=device_id,
                user_id=user_id,
                stored=existing.fingerprint_hash[:8],
                received=fp_hash[:8],
            )
        # Update last-seen metadata
        await repo.touch(device_id, ip_address=ip_address, user_agent=user_agent)

    return device_id


async def list_devices(db: AsyncSession, user_id: str) -> list[DeviceRegistration]:
    """Return all registered devices for a user."""
    return await DeviceRepository(db).list_by_user(user_id)


async def revoke_device(db: AsyncSession, user_id: str, device_id: str) -> bool:
    """
    Revoke a device registration.  Returns True if the device was found and
    belonged to the user, False otherwise.
    """
    repo = DeviceRepository(db)
    device = await repo.get(device_id)
    if not device or device.user_id != user_id:
        return False
    await repo.delete(device_id)
    logger.info("device_revoked", device_id=device_id, user_id=user_id)
    return True
