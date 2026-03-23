import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from pe_common.schemas import success_response
from pe_common.exceptions import AppException

from ..database import get_db
from ..domains.users.repository import UserRepository, AddressRepository
from ..domains.users.schemas import UserResponse, AddressResponse
from ..domains.users.service import UserService
from ..domains.tenants.repository import TenantRepository
from ..domains.tenants.schemas import TenantResponse
from ..domains.rbac.service import RbacService
from ..domains.rbac.schemas import PermissionCheckRequest

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class GetOrCreateRequest(BaseModel):
    mobile: str


class PermissionCheckBody(BaseModel):
    resource: str
    action: str


# ─── Called by auth-service after OTP verification ───────────────────────────

@router.post("/users/get-or-create")
async def get_or_create_user(
    body: GetOrCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    rbac_svc = RbacService(db)

    user = await svc.get_or_create_by_mobile(body.mobile)

    # Assign customer role on first creation
    role_names = await rbac_svc.get_user_role_names(user.id)
    if not role_names:
        await rbac_svc.assign_default_customer_role(user.id)

    await db.commit()

    return success_response({"user_id": str(user.id)})


# ─── User lookups ─────────────────────────────────────────────────────────────

@router.get("/users/{user_id}")
async def get_user_by_id(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    user = await repo.get_by_id(uuid.UUID(user_id))
    if not user:
        raise AppException(code="NOT_FOUND", message="User not found", status_code=404)
    return success_response(UserResponse.model_validate(user).model_dump())


@router.get("/users/{user_id}/addresses")
async def get_user_addresses(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    repo = AddressRepository(db)
    addresses = await repo.get_by_user(uuid.UUID(user_id))
    return success_response([AddressResponse.model_validate(a).model_dump() for a in addresses])


@router.get("/users/{user_id}/roles")
async def get_user_roles(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    svc = RbacService(db)
    roles = await svc.get_user_role_names(uuid.UUID(user_id))
    return success_response({"roles": roles})


# ─── Permission check ─────────────────────────────────────────────────────────

@router.post("/users/{user_id}/permissions/check")
async def check_permission(
    user_id: str,
    body: PermissionCheckBody,
    db: AsyncSession = Depends(get_db),
):
    svc = RbacService(db)
    allowed = await svc.check_permission(uuid.UUID(user_id), body.resource, body.action)
    return success_response({"allowed": allowed, "user_id": user_id,
                             "resource": body.resource, "action": body.action})


# ─── Tenant lookup ────────────────────────────────────────────────────────────

@router.get("/tenants/{tenant_id}")
async def get_tenant_by_id(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    repo = TenantRepository(db)
    tenant = await repo.get_by_id(uuid.UUID(tenant_id))
    if not tenant:
        raise AppException(code="NOT_FOUND", message="Tenant not found", status_code=404)
    return success_response(TenantResponse.model_validate(tenant).model_dump())