import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.auth import OtpRequest, Session, MfaConfig, SocialAccount


class OtpRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, mobile: str, otp_hash: str, expires_at: datetime) -> OtpRequest:
        record = OtpRequest(
            id=str(uuid.uuid4()),
            mobile=mobile,
            otp_hash=otp_hash,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record


class SessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: str,
        refresh_token_hash: str,
        expires_at: datetime,
        tenant_id: str = None,
        device_info: str = None,
        ip_address: str = None,
    ) -> Session:
        session = Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            device_info=device_info,
            ip_address=ip_address,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_by_id(self, session_id: str) -> Session | None:
        result = await self.db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def get_active_by_user(self, user_id: str) -> list[Session]:
        result = await self.db.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.expires_at > datetime.now(timezone.utc),
            )
        )
        return list(result.scalars().all())

    async def revoke(self, session_id: str) -> bool:
        result = await self.db.execute(
            update(Session)
            .where(Session.id == session_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return result.rowcount > 0

    async def revoke_all_user_sessions(self, user_id: str):
        await self.db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.db.commit()


class MfaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user(self, user_id: str) -> MfaConfig | None:
        result = await self.db.execute(
            select(MfaConfig).where(MfaConfig.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: str, totp_secret: str) -> MfaConfig:
        existing = await self.get_by_user(user_id)
        if existing:
            existing.totp_secret_encrypted = totp_secret
            await self.db.commit()
            return existing
        config = MfaConfig(
            id=str(uuid.uuid4()),
            user_id=user_id,
            totp_secret_encrypted=totp_secret,
            is_enabled=False,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def enable(self, user_id: str):
        await self.db.execute(
            update(MfaConfig)
            .where(MfaConfig.user_id == user_id)
            .values(is_enabled=True)
        )
        await self.db.commit()

class SocialAccountRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_provider(self, provider: str, provider_user_id: str) -> SocialAccount | None:
        result = await self.db.execute(
            select(SocialAccount).where(
                SocialAccount.provider == provider,
                SocialAccount.provider_user_id == provider_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: str, provider: str, provider_user_id: str,
                     access_token: str | None = None) -> SocialAccount:
        existing = await self.get_by_provider(provider, provider_user_id)
        if existing:
            existing.user_id = user_id
            if access_token:
                existing.access_token_encrypted = access_token
            await self.db.commit()
            return existing
        account = SocialAccount(
            id=str(uuid.uuid4()),
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            access_token_encrypted=access_token,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account
