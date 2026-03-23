from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.schemas import success_response
from pe_common.auth import get_current_user
from pe_common.exceptions import AppException

from ...database import get_db
from .schemas import TenantRegister, TenantUpdate, TenantResponse, TenantRejectRequest
from .service import TenantService

router = APIRouter(tags=["tenants"])


# ─── My Tenant ────────────────────────────────────────────────────────────────

@router.post("/api/v1/tenants/register")
async def register_tenant(
    body: TenantRegister,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = TenantService(db)
    tenant = await svc.register_tenant(uuid.UUID(current_user["user_id"]), body)
    await db.commit()
    return success_response(TenantResponse.model_validate(tenant).model_dump())


@router.get("/api/v1/tenants/me")
async def get_my_tenant(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = TenantService(db)
    tenant = await svc.get_my_tenant(uuid.UUID(current_user["user_id"]))
    return success_response(TenantResponse.model_validate(tenant).model_dump())


@router.patch("/api/v1/tenants/me")
async def update_my_tenant(
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = TenantService(db)
    tenant = await svc.update_my_tenant(uuid.UUID(current_user["user_id"]), body)
    await db.commit()
    return success_response(TenantResponse.model_validate(tenant).model_dump())


@router.post("/api/v1/tenants/me/logo")
async def upload_tenant_logo(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    file_url = body.get("file_url")
    if not file_url:
        raise AppException(code="VALIDATION_ERROR", message="file_url is required", status_code=422)
    svc = TenantService(db)
    tenant = await svc.get_my_tenant(uuid.UUID(current_user["user_id"]))
    from .repository import TenantRepository
    repo = TenantRepository(db)
    tenant = await repo.update(tenant, logo_url=file_url)
    await db.commit()
    return success_response({"logo_url": tenant.logo_url})


@router.get("/api/v1/tenants/{tenant_id}")
async def get_tenant_public(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    import uuid
    from .repository import TenantRepository
    repo = TenantRepository(db)
    tenant = await repo.get_by_id(uuid.UUID(tenant_id))
    if not tenant:
        raise AppException(code="NOT_FOUND", message="Tenant not found", status_code=404)
    return success_response(TenantResponse.model_validate(tenant).model_dump())


# ─── Admin: Tenants ───────────────────────────────────────────────────────────

@router.get("/api/v1/admin/tenants")
async def admin_list_tenants(
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    from .repository import TenantRepository
    repo = TenantRepository(db)
    offset = (page - 1) * per_page
    tenants = await repo.list_all(status=status, limit=per_page, offset=offset)
    return success_response([TenantResponse.model_validate(t).model_dump() for t in tenants])


@router.patch("/api/v1/admin/tenants/{tenant_id}/approve")
async def admin_approve_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    _require_admin(current_user)
    svc = TenantService(db)
    tenant = await svc.approve_tenant(uuid.UUID(tenant_id), uuid.UUID(current_user["user_id"]))
    await db.commit()
    return success_response(TenantResponse.model_validate(tenant).model_dump())


@router.patch("/api/v1/admin/tenants/{tenant_id}/reject")
async def admin_reject_tenant(
    tenant_id: str,
    body: TenantRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    _require_admin(current_user)
    svc = TenantService(db)
    tenant = await svc.reject_tenant(uuid.UUID(tenant_id), uuid.UUID(current_user["user_id"]), body.reason)
    await db.commit()
    return success_response(TenantResponse.model_validate(tenant).model_dump())


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _require_admin(current_user: dict):
    roles = current_user.get("roles", [])
    if not any(r in roles for r in ("super_admin", "admin")):
        raise AppException(code="PERMISSION_DENIED", message="Admin access required", status_code=403)