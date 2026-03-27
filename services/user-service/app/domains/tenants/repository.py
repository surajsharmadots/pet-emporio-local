import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .models import Tenant


class TenantRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == str(tenant_id))
        )
        return result.scalar_one_or_none()

    async def get_by_owner(self, owner_user_id: uuid.UUID) -> Tenant | None:
        result = await self.db.execute(
            select(Tenant).where(Tenant.owner_user_id == str(owner_user_id))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.db.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Tenant:
        tenant = Tenant(**data)
        self.db.add(tenant)
        await self.db.flush()
        await self.db.refresh(tenant)
        return tenant

    async def update(self, tenant: Tenant, **kwargs) -> Tenant:
        for key, value in kwargs.items():
            setattr(tenant, key, value)
        await self.db.flush()
        await self.db.refresh(tenant)
        return tenant

    async def list_all(self, status: str | None = None, limit: int = 50, offset: int = 0) -> list[Tenant]:
        query = select(Tenant)
        if status:
            query = query.where(Tenant.status == status)
        query = query.order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())