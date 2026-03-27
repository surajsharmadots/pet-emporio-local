import csv
import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.schemas import success_response
from pe_common.auth import get_current_user
from pe_common.exceptions import AppException

from ...database import get_db
from .schemas import (
    RoleResponse, PermissionResponse, RoleAssignRequest,
    RoleCreate, RoleUpdate, RolePermissionAssign,
    SubAdminCreate, SubAdminUpdate, SubAdminDeactivate,
)
from .service import RbacService

router = APIRouter(tags=["rbac"])


def _require_admin(current_user: dict):
    roles = current_user.get("roles", [])
    if not any(r in roles for r in ("super_admin", "admin")):
        raise AppException(code="PERMISSION_DENIED", message="Admin access required", status_code=403)


def _require_super_admin(current_user: dict):
    if "super_admin" not in current_user.get("roles", []):
        raise AppException(code="PERMISSION_DENIED", message="Super admin access required", status_code=403)


@router.get("/api/v1/admin/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    svc = RbacService(db)
    roles = await svc.list_roles()
    return success_response([RoleResponse.model_validate(r).model_dump() for r in roles])


@router.get("/api/v1/admin/permissions")
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    svc = RbacService(db)
    perms = await svc.list_permissions()
    return success_response([PermissionResponse.model_validate(p).model_dump() for p in perms])


@router.post("/api/v1/admin/roles")
async def create_role(
    body: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    svc = RbacService(db)
    role = await svc.create_role(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
    )
    await db.commit()
    return success_response(RoleResponse.model_validate(role).model_dump())


@router.patch("/api/v1/admin/roles/{role_id}")
async def update_role(
    role_id: str,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    svc = RbacService(db)
    role = await svc.update_role(role_id, body.display_name, body.description)
    await db.commit()
    return success_response(RoleResponse.model_validate(role).model_dump())


@router.delete("/api/v1/admin/roles/{role_id}")
async def deactivate_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    svc = RbacService(db)
    await svc.deactivate_role(role_id)
    await db.commit()
    return success_response({"message": "Role deactivated"})


@router.get("/api/v1/admin/roles/{role_id}/users")
async def list_users_by_role(
    role_id: str,
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    svc = RbacService(db)
    offset = (page - 1) * per_page
    user_roles = await svc.get_users_by_role(role_id, limit=per_page, offset=offset)
    return success_response([
        {"user_id": ur.user_id, "tenant_id": ur.tenant_id, "granted_at": ur.granted_at.isoformat() if ur.granted_at else None, "is_active": ur.is_active}
        for ur in user_roles
    ])


@router.get("/api/v1/admin/roles/{role_id}/permissions")
async def list_role_permissions(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    svc = RbacService(db)
    rps = await svc.get_role_permissions(role_id)
    return success_response([
        PermissionResponse.model_validate(rp.permission).model_dump()
        for rp in rps
    ])


@router.post("/api/v1/admin/roles/{role_id}/permissions")
async def assign_permission_to_role(
    role_id: str,
    body: RolePermissionAssign,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    svc = RbacService(db)
    await svc.assign_permission_to_role(role_id, str(body.permission_id))
    await db.commit()
    return success_response({"message": "Permission assigned to role"})


@router.delete("/api/v1/admin/roles/{role_id}/permissions/{permission_id}")
async def revoke_permission_from_role(
    role_id: str,
    permission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    svc = RbacService(db)
    await svc.revoke_permission_from_role(role_id, permission_id)
    await db.commit()
    return success_response({"message": "Permission revoked from role"})


@router.post("/api/v1/admin/users/{user_id}/roles/assign")
async def assign_role(
    user_id: str,
    body: RoleAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import uuid
    _require_admin(current_user)
    svc = RbacService(db)
    await svc.assign_role(
        user_id=uuid.UUID(user_id),
        role_name=body.role_name,
        tenant_id=body.tenant_id,
        granted_by=uuid.UUID(current_user["user_id"]),
    )
    await db.commit()
    return success_response({"message": f"Role '{body.role_name}' assigned to user {user_id}"})


@router.get("/api/v1/admin/sub-admins")
async def list_sub_admins(
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    from ..users.repository import UserRepository
    from ...enums import UserType
    from sqlalchemy import select
    from ..users.models import User
    repo = UserRepository(db)
    offset = (page - 1) * per_page
    result = await db.execute(
        select(User)
        .where(User.user_type.in_(["admin", "super_admin", "catalog_manager"]))
        .where(User.deleted_at.is_(None))
        .limit(per_page)
        .offset(offset)
    )
    users = result.scalars().all()
    return success_response([
        {
            "id": u.id,
            "mobile": u.mobile,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "full_name": u.full_name,
            "user_type": u.user_type,
            "is_active": u.is_active,
        }
        for u in users
    ])


@router.post("/api/v1/admin/sub-admins")
async def create_sub_admin(
    body: SubAdminCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    from ..users.repository import UserRepository
    from ..users.models import User
    repo = UserRepository(db)

    existing = await repo.get_by_mobile(body.mobile)
    if existing:
        raise AppException(code="CONFLICT", message="User with this mobile already exists", status_code=409)

    user = await repo.create(
        mobile=body.mobile,
        email=body.email,
        first_name=body.first_name,
        last_name=body.last_name,
        full_name=f"{body.first_name} {body.last_name}",
        user_type="admin",
    )

    svc = RbacService(db)
    role = await svc.role_repo.get_by_id(str(body.role_id))
    if role:
        await svc.user_role_repo.assign_role(user.id, role.id, None, current_user["user_id"])

    await db.commit()
    return success_response({
        "user_id": user.id,
        "mobile": user.mobile,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    })


@router.get("/api/v1/admin/sub-admins/export")
async def export_sub_admins(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    from ..users.models import User
    from sqlalchemy import select
    result = await db.execute(
        select(User)
        .where(User.user_type.in_(["admin", "super_admin", "catalog_manager"]))
        .where(User.deleted_at.is_(None))
    )
    users = result.scalars().all()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "mobile", "email", "first_name", "last_name", "user_type", "is_active", "created_at"])
    writer.writeheader()
    for u in users:
        writer.writerow({
            "id": u.id,
            "mobile": u.mobile,
            "email": u.email or "",
            "first_name": u.first_name or "",
            "last_name": u.last_name or "",
            "user_type": u.user_type,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else "",
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sub-admins.csv"},
    )


@router.get("/api/v1/admin/sub-admins/{user_id}")
async def get_sub_admin(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    from ..users.repository import UserRepository
    repo = UserRepository(db)
    import uuid
    user = await repo.get_by_id(uuid.UUID(user_id))
    if not user:
        raise AppException(code="NOT_FOUND", message="Sub-admin not found", status_code=404)
    return success_response({
        "id": user.id,
        "mobile": user.mobile,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "user_type": user.user_type,
        "is_active": user.is_active,
    })


@router.patch("/api/v1/admin/sub-admins/{user_id}")
async def update_sub_admin(
    user_id: str,
    body: SubAdminUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    from ..users.repository import UserRepository
    import uuid
    repo = UserRepository(db)
    user = await repo.get_by_id(uuid.UUID(user_id))
    if not user:
        raise AppException(code="NOT_FOUND", message="Sub-admin not found", status_code=404)

    update_data = body.model_dump(exclude_none=True)
    if "first_name" in update_data or "last_name" in update_data:
        fn = update_data.get("first_name", user.first_name or "")
        ln = update_data.get("last_name", user.last_name or "")
        update_data["full_name"] = f"{fn} {ln}".strip()

    if "role_id" in update_data:
        role_id = str(update_data.pop("role_id"))
        svc = RbacService(db)
        role = await svc.role_repo.get_by_id(role_id)
        if role:
            await svc.user_role_repo.assign_role(user_id, role.id, None, current_user["user_id"])

    user = await repo.update(user, **update_data)
    await db.commit()
    return success_response({
        "id": user.id,
        "mobile": user.mobile,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
    })


@router.patch("/api/v1/admin/sub-admins/{user_id}/deactivate")
async def deactivate_sub_admin(
    user_id: str,
    body: SubAdminDeactivate,
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    svc = RbacService(db)
    await svc.deactivate_sub_admin(user_id, role_id, body.reason)
    await db.commit()
    return success_response({"message": "Sub-admin deactivated"})


@router.patch("/api/v1/admin/sub-admins/{user_id}/activate")
async def activate_sub_admin(
    user_id: str,
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_super_admin(current_user)
    svc = RbacService(db)
    await svc.reactivate_sub_admin(user_id, role_id)
    await db.commit()
    return success_response({"message": "Sub-admin activated"})