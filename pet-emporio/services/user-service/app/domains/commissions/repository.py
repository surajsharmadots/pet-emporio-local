from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from .models import CommissionConfig


class CommissionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> list[CommissionConfig]:
        result = await self.db.execute(
            select(CommissionConfig).order_by(CommissionConfig.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, config_id: str) -> CommissionConfig | None:
        result = await self.db.execute(
            select(CommissionConfig).where(CommissionConfig.id == str(config_id))
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> CommissionConfig:
        config = CommissionConfig(**kwargs)
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return config

    async def update(self, config: CommissionConfig, **kwargs) -> CommissionConfig:
        for key, value in kwargs.items():
            setattr(config, key, value)
        await self.db.flush()
        await self.db.refresh(config)
        return config

    async def resolve_for_tenant(self, tenant_id: str, tenant_type: str | None = None) -> CommissionConfig | None:
        """
        Priority: tenant-specific > tenant_type > platform
        Returns the active config for today.
        """
        today = date.today()
        active_filter = and_(
            CommissionConfig.effective_from <= today,
            or_(CommissionConfig.effective_to.is_(None), CommissionConfig.effective_to >= today),
        )

        # 1. Tenant-specific
        result = await self.db.execute(
            select(CommissionConfig)
            .where(and_(CommissionConfig.scope == "tenant", CommissionConfig.tenant_id == tenant_id, active_filter))
            .order_by(CommissionConfig.effective_from.desc())
            .limit(1)
        )
        config = result.scalar_one_or_none()
        if config:
            return config

        # 2. Tenant-type level
        if tenant_type:
            result = await self.db.execute(
                select(CommissionConfig)
                .where(and_(CommissionConfig.scope == "tenant_type", CommissionConfig.tenant_type == tenant_type, active_filter))
                .order_by(CommissionConfig.effective_from.desc())
                .limit(1)
            )
            config = result.scalar_one_or_none()
            if config:
                return config

        # 3. Platform default
        result = await self.db.execute(
            select(CommissionConfig)
            .where(and_(CommissionConfig.scope == "platform", active_filter))
            .order_by(CommissionConfig.effective_from.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()