import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


def _uuid():
    return str(uuid.uuid4())


def _utc_now():
    return datetime.now(timezone.utc)


class OtpRequest(Base):
    __tablename__ = "otp_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mobile: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    otp_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # For Keycloak-issued tokens we store the KC refresh token hash.
    # For legacy self-issued tokens the UUID refresh token hash is stored.
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # kc_user_id links this session to the Keycloak user record.
    kc_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_social_provider_uid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Field is intentionally nullable; we do NOT persist provider access tokens
    # for security reasons — the name is kept for schema compatibility.
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class MfaConfig(Base):
    __tablename__ = "mfa_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    # TOTP secret encrypted with Fernet (symmetric) before storage.
    totp_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class DeviceRegistration(Base):
    """
    Tracks devices that have authenticated on behalf of a user.

    device_id   – UUID generated and persisted on the client device.
    fingerprint_hash – SHA-256 of OS + model + other stable signals,
                  used to detect SIM swaps / stolen tokens.
    kc_user_id  – Keycloak user UUID for cross-referencing sessions.
    """
    __tablename__ = "device_registrations"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_device_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kc_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    fingerprint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)