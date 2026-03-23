import re
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.exceptions import AppException
from pe_common.logging import get_logger

from .repository import TenantRepository
from .schemas import TenantRegister, TenantUpdate
from ..audit.repository import AuditRepository

logger = get_logger(__name__)


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:90]


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TenantRepository(db)
        self.audit_repo = AuditRepository(db)

    async def register_tenant(self, owner_user_id, data: TenantRegister):
        owner_id_str = str(owner_user_id)

        existing = await self.repo.get_by_owner(owner_id_str)
        if existing:
            raise AppException(
                code="CONFLICT",
                message="User already has a registered tenant",
                status_code=409,
            )

        base_slug = _slugify(data.business_name)
        slug = base_slug
        counter = 1
        while await self.repo.get_by_slug(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1

        tenant = await self.repo.create({
            "name": data.business_name,
            "slug": slug,
            "owner_user_id": owner_id_str,
            "tenant_type": data.tenant_type,
            "gst_number": data.gst_number,
            "pan_number": data.pan_number,
            "status": "pending",
            "settings": {},
        })
        logger.info("tenant_registered", tenant_id=str(tenant.id), owner=owner_id_str)
        return tenant

    async def get_my_tenant(self, owner_user_id):
        tenant = await self.repo.get_by_owner(str(owner_user_id))
        if not tenant:
            raise AppException(code="NOT_FOUND", message="No tenant found for this user", status_code=404)
        return tenant

    async def update_my_tenant(self, owner_user_id, data: TenantUpdate):
        tenant = await self.repo.get_by_owner(str(owner_user_id))
        if not tenant:
            raise AppException(code="NOT_FOUND", message="Tenant not found", status_code=404)
        update_data = data.model_dump(exclude_none=True)
        return await self.repo.update(tenant, **update_data)

    async def approve_tenant(self, tenant_id, approver_id):
        tenant = await self.repo.get_by_id(str(tenant_id))
        if not tenant:
            raise AppException(code="NOT_FOUND", message="Tenant not found", status_code=404)
        if tenant.status == "active":
            raise AppException(code="CONFLICT", message="Tenant is already approved", status_code=409)

        old_status = tenant.status
        tenant = await self.repo.update(
            tenant,
            status="active",
            approved_by=str(approver_id),
            approved_at=datetime.now(timezone.utc),
        )

        await self.audit_repo.log(
            user_id=str(approver_id),
            action="admin.tenant.approve",
            resource_type="tenant",
            resource_id=str(tenant_id),
            old_values={"status": old_status},
            new_values={"status": "active"},
        )

        try:
            from pe_common.events import EventPublisher
            await EventPublisher.publish(
                event_type="tenant.approved",
                payload={
                    "tenant_id": str(tenant_id),
                    "tenant_type": tenant.tenant_type,
                    "owner_user_id": str(tenant.owner_user_id),
                },
                service="user-service",
            )
        except Exception as e:
            logger.warning("event_publish_failed", error=str(e))

        return tenant

    async def reject_tenant(self, tenant_id, approver_id, reason: str):
        tenant = await self.repo.get_by_id(str(tenant_id))
        if not tenant:
            raise AppException(code="NOT_FOUND", message="Tenant not found", status_code=404)

        old_status = tenant.status
        tenant = await self.repo.update(
            tenant,
            status="rejected",
            rejection_reason=reason,
        )

        await self.audit_repo.log(
            user_id=str(approver_id),
            action="admin.tenant.reject",
            resource_type="tenant",
            resource_id=str(tenant_id),
            old_values={"status": old_status},
            new_values={"status": "rejected", "rejection_reason": reason},
        )

        try:
            from pe_common.events import EventPublisher
            await EventPublisher.publish(
                event_type="tenant.rejected",
                payload={
                    "tenant_id": str(tenant_id),
                    "owner_user_id": str(tenant.owner_user_id),
                    "reason": reason,
                },
                service="user-service",
            )
        except Exception as e:
            logger.warning("event_publish_failed", error=str(e))

        return tenant