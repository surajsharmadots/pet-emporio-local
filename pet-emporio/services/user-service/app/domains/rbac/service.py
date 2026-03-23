import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.exceptions import AppException
from pe_common.logging import get_logger

from .repository import RoleRepository, PermissionRepository, RolePermissionRepository, UserRoleRepository

logger = get_logger(__name__)

SYSTEM_ROLES = [
    {"name": "super_admin", "display_name": "Super Admin", "description": "Full system access"},
    {"name": "admin", "display_name": "Admin", "description": "Platform admin"},
    {"name": "catalog_manager", "display_name": "Catalog Manager", "description": "Manage products"},
    {"name": "customer", "display_name": "Customer", "description": "Default customer role"},
    {"name": "seller", "display_name": "Seller", "description": "Seller portal access"},
    {"name": "doctor", "display_name": "Doctor", "description": "Veterinary doctor portal"},
    {"name": "lab_technician", "display_name": "Lab Technician", "description": "Lab portal access"},
    {"name": "groomer", "display_name": "Groomer", "description": "Groomer portal access"},
    {"name": "pharmacist", "display_name": "Pharmacist", "description": "Pharmacy portal access"},
]


class RbacService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.role_repo = RoleRepository(db)
        self.perm_repo = PermissionRepository(db)
        self.rp_repo = RolePermissionRepository(db)
        self.user_role_repo = UserRoleRepository(db)

    async def seed_roles(self):
        for role_data in SYSTEM_ROLES:
            await self.role_repo.get_or_create(
                name=role_data["name"],
                display_name=role_data["display_name"],
                is_system=True,
            )
        await self.db.commit()

    async def list_roles(self) -> list:
        return await self.role_repo.list_all()

    async def list_permissions(self) -> list:
        return await self.perm_repo.list_all()

    async def assign_role(self, user_id: uuid.UUID, role_name: str,
                          tenant_id: uuid.UUID | None, granted_by: uuid.UUID):
        role = await self.role_repo.get_by_name(role_name)
        if not role:
            raise AppException(code="NOT_FOUND", message=f"Role '{role_name}' not found", status_code=404)
        return await self.user_role_repo.assign_role(user_id, role.id, tenant_id, granted_by)

    async def assign_default_customer_role(self, user_id: uuid.UUID):
        role = await self.role_repo.get_by_name("customer")
        if role:
            await self.user_role_repo.assign_role(user_id, role.id, None, None)

    async def get_user_role_names(self, user_id: uuid.UUID) -> list[str]:
        return await self.user_role_repo.get_role_names(user_id)

    async def check_permission(self, user_id: uuid.UUID, resource: str, action: str) -> bool:
        return await self.user_role_repo.check_permission(user_id, resource, action)

    # ── Role CRUD ──────────────────────────────────────────────────────────────

    async def create_role(self, name: str, display_name: str, description: str | None = None):
        existing = await self.role_repo.get_by_name(name)
        if existing:
            raise AppException(code="CONFLICT", message=f"Role '{name}' already exists", status_code=409)
        return await self.role_repo.create(name=name, display_name=display_name, description=description)

    async def update_role(self, role_id: str, display_name: str | None, description: str | None):
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise AppException(code="NOT_FOUND", message="Role not found", status_code=404)
        return await self.role_repo.update(role, display_name=display_name, description=description)

    async def deactivate_role(self, role_id: str):
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise AppException(code="NOT_FOUND", message="Role not found", status_code=404)
        if role.is_system:
            raise AppException(code="FORBIDDEN", message="System roles cannot be deactivated", status_code=403)
        return await self.role_repo.deactivate(role)

    async def get_users_by_role(self, role_id: str, limit: int = 50, offset: int = 0):
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise AppException(code="NOT_FOUND", message="Role not found", status_code=404)
        return await self.user_role_repo.get_users_by_role(role_id, limit=limit, offset=offset)

    # ── Role Permissions ───────────────────────────────────────────────────────

    async def get_role_permissions(self, role_id: str):
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise AppException(code="NOT_FOUND", message="Role not found", status_code=404)
        return await self.rp_repo.list_by_role(role_id)

    async def assign_permission_to_role(self, role_id: str, permission_id: str):
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise AppException(code="NOT_FOUND", message="Role not found", status_code=404)
        perm = await self.rp_repo.get_permission_by_id(permission_id)
        if not perm:
            raise AppException(code="NOT_FOUND", message="Permission not found", status_code=404)
        return await self.rp_repo.assign(role_id, permission_id)

    async def revoke_permission_from_role(self, role_id: str, permission_id: str):
        removed = await self.rp_repo.revoke(role_id, permission_id)
        if not removed:
            raise AppException(code="NOT_FOUND", message="Permission not assigned to this role", status_code=404)

    # ── Sub-Admin Management ───────────────────────────────────────────────────

    async def deactivate_sub_admin(self, user_id: str, role_id: str, reason: str):
        ur = await self.user_role_repo.get_by_user_and_role(user_id, role_id)
        if not ur:
            raise AppException(code="NOT_FOUND", message="User role assignment not found", status_code=404)
        return await self.user_role_repo.deactivate_user_role(ur, reason)

    async def reactivate_sub_admin(self, user_id: str, role_id: str):
        ur = await self.user_role_repo.get_by_user_and_role(user_id, role_id)
        if not ur:
            raise AppException(code="NOT_FOUND", message="User role assignment not found", status_code=404)
        return await self.user_role_repo.reactivate_user_role(ur)