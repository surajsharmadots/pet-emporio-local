from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from pe_common.schemas import success_response, paginated_response
from pe_common.auth import get_current_user
from pe_common.exceptions import AppException

from ...database import get_db
from .schemas import (
    UserUpdate, UserResponse, AddressCreate, AddressUpdate,
    AddressResponse, KycUploadRequest, KycDocumentResponse, AdminUserUpdate,
    CompleteRegistrationRequest, WalkInCustomerCreate, WalkInCustomerResponse,
)
from .service import UserService
from ..rbac.service import RbacService

router = APIRouter(tags=["users"])


# ─── My Profile ───────────────────────────────────────────────────────────────

@router.get("/api/v1/users/me")
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    svc = UserService(db)
    rbac_svc = RbacService(db)
    user = await svc.get_profile(uuid.UUID(current_user["user_id"]))
    roles = await rbac_svc.get_user_role_names(user.id)
    data = UserResponse.model_validate(user).model_dump()
    data["roles"] = roles
    return success_response(data)


@router.patch("/api/v1/users/me")
async def update_my_profile(
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = UserService(db)
    user = await svc.update_profile(uuid.UUID(current_user["user_id"]), body)
    return success_response(UserResponse.model_validate(user).model_dump())


# ─── Complete Registration ────────────────────────────────────────────────────

@router.post("/api/v1/users/me/complete-registration")
async def complete_registration(
    body: CompleteRegistrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = UserService(db)
    user = await svc.complete_registration(uuid.UUID(current_user["user_id"]), body)
    await db.commit()
    return success_response(UserResponse.model_validate(user).model_dump())


# ─── Provider: Walk-In Customers ──────────────────────────────────────────────

@router.post("/api/v1/provider/walk-in-customers")
async def create_walk_in_customer(
    body: WalkInCustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    provider_tenant_id = current_user.get("tenant_id")
    if not provider_tenant_id:
        raise AppException(code="FORBIDDEN", message="Provider tenant context required", status_code=403)
    svc = UserService(db)
    user = await svc.create_walk_in_customer(provider_tenant_id, body)
    await db.commit()
    return success_response(WalkInCustomerResponse(
        user_id=str(user.id),
        first_name=user.first_name,
        last_name=user.last_name,
        mobile=user.mobile,
    ).model_dump())


@router.get("/api/v1/provider/walk-in-customers")
async def list_walk_in_customers(
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from pe_common.schemas import paginated_response
    provider_tenant_id = current_user.get("tenant_id")
    if not provider_tenant_id:
        raise AppException(code="FORBIDDEN", message="Provider tenant context required", status_code=403)
    svc = UserService(db)
    offset = (page - 1) * per_page
    users = await svc.list_walk_in_customers(provider_tenant_id, limit=per_page, offset=offset)
    return success_response([
        WalkInCustomerResponse(
            user_id=str(u.id),
            first_name=u.first_name,
            last_name=u.last_name,
            mobile=u.mobile,
        ).model_dump()
        for u in users
    ])


# ─── Avatar ───────────────────────────────────────────────────────────────────

@router.post("/api/v1/users/me/avatar")
async def upload_avatar(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    file_url = body.get("file_url")
    if not file_url:
        raise AppException(code="VALIDATION_ERROR", message="file_url is required", status_code=422)
    svc = UserService(db)
    user = await svc.repo.get_by_id(uuid.UUID(current_user["user_id"]))
    if not user:
        raise AppException(code="NOT_FOUND", message="User not found", status_code=404)
    user = await svc.repo.update(user, avatar_url=file_url)
    await db.commit()
    return success_response({"avatar_url": user.avatar_url})


# ─── Addresses ────────────────────────────────────────────────────────────────

@router.get("/api/v1/users/me/addresses")
async def list_my_addresses(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = UserService(db)
    addresses = await svc.list_addresses(uuid.UUID(current_user["user_id"]))
    return success_response([AddressResponse.model_validate(a).model_dump() for a in addresses])


@router.post("/api/v1/users/me/addresses")
async def add_address(
    body: AddressCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = UserService(db)
    address = await svc.add_address(uuid.UUID(current_user["user_id"]), body)
    await db.commit()
    return success_response(AddressResponse.model_validate(address).model_dump())


@router.patch("/api/v1/users/me/addresses/{address_id}")
async def update_address(
    address_id: str,
    body: AddressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = UserService(db)
    address = await svc.update_address(
        uuid.UUID(current_user["user_id"]),
        uuid.UUID(address_id),
        body,
    )
    await db.commit()
    return success_response(AddressResponse.model_validate(address).model_dump())


@router.delete("/api/v1/users/me/addresses/{address_id}")
async def delete_address(
    address_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = UserService(db)
    await svc.delete_address(uuid.UUID(current_user["user_id"]), uuid.UUID(address_id))
    await db.commit()
    return success_response({"message": "Address deleted"})


# ─── KYC ──────────────────────────────────────────────────────────────────────

@router.post("/api/v1/users/me/kyc/upload")
async def upload_kyc(
    body: KycUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = UserService(db)
    doc = await svc.upload_kyc(uuid.UUID(current_user["user_id"]), body.doc_type, body.file_url)
    await db.commit()
    return success_response(KycDocumentResponse.model_validate(doc).model_dump())


@router.get("/api/v1/users/me/kyc/status")
async def kyc_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    svc = UserService(db)
    docs = await svc.get_kyc_status(uuid.UUID(current_user["user_id"]))
    return success_response([KycDocumentResponse.model_validate(d).model_dump() for d in docs])


# ─── Admin: Users ─────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/users")
async def admin_list_users(
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    svc = UserService(db)
    offset = (page - 1) * per_page
    users = await svc.repo.list_all(limit=per_page, offset=offset)
    total = await svc.repo.count_all()
    return paginated_response(
        [UserResponse.model_validate(u).model_dump() for u in users],
        page=page, page_size=per_page, total=total,
    )


@router.get("/api/v1/admin/users/{user_id}")
async def admin_get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    _require_admin(current_user)
    svc = UserService(db)
    user = await svc.get_profile(uuid.UUID(user_id))
    return success_response(UserResponse.model_validate(user).model_dump())


@router.patch("/api/v1/admin/users/{user_id}")
async def admin_update_user(
    user_id: str,
    body: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    _require_admin(current_user)
    svc = UserService(db)
    user = await svc.admin_update_user(
        uuid.UUID(user_id), body, uuid.UUID(current_user["user_id"])
    )
    await db.commit()
    return success_response(UserResponse.model_validate(user).model_dump())


# ─── Admin: KYC ───────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/kyc")
async def admin_list_kyc(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    svc = UserService(db)
    docs = await svc.kyc_repo.list_pending()
    return success_response([KycDocumentResponse.model_validate(d).model_dump() for d in docs])


@router.patch("/api/v1/admin/kyc/{kyc_id}/approve")
async def admin_approve_kyc(
    kyc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    _require_admin(current_user)
    svc = UserService(db)
    doc = await svc.approve_kyc(uuid.UUID(kyc_id), uuid.UUID(current_user["user_id"]))
    await db.commit()
    return success_response(KycDocumentResponse.model_validate(doc).model_dump())


@router.patch("/api/v1/admin/kyc/{kyc_id}/reject")
async def admin_reject_kyc(
    kyc_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    _require_admin(current_user)
    svc = UserService(db)
    doc = await svc.reject_kyc(
        uuid.UUID(kyc_id),
        uuid.UUID(current_user["user_id"]),
        body.get("reason", ""),
    )
    await db.commit()
    return success_response(KycDocumentResponse.model_validate(doc).model_dump())


# ─── Admin: Audit logs ────────────────────────────────────────────────────────

@router.get("/api/v1/admin/audit-logs")
async def admin_audit_logs(
    page: int = 1,
    per_page: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    from ..audit.repository import AuditRepository
    audit_repo = AuditRepository(db)
    offset = (page - 1) * per_page
    logs = await audit_repo.list_all(limit=per_page, offset=offset)
    return success_response([
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _require_admin(current_user: dict):
    roles = current_user.get("roles", [])
    if not any(r in roles for r in ("super_admin", "admin")):
        raise AppException(code="PERMISSION_DENIED", message="Admin access required", status_code=403)