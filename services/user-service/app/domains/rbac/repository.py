from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .models import Role, Permission, RolePermission, UserRole


class RoleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_name(self, name: str) -> Role | None:
        result = await self.db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def get_by_id(self, role_id: str) -> Role | None:
        result = await self.db.execute(select(Role).where(Role.id == str(role_id)))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Role]:
        result = await self.db.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())

    async def create(self, name: str, display_name: str, description: str | None = None,
                     is_system: bool = False) -> Role:
        role = Role(name=name, display_name=display_name, description=description, is_system=is_system)
        self.db.add(role)
        await self.db.flush()
        await self.db.refresh(role)
        return role

    async def get_or_create(self, name: str, display_name: str, is_system: bool = False) -> Role:
        role = await self.get_by_name(name)
        if not role:
            role = await self.create(name, display_name, is_system=is_system)
        return role

    async def update(self, role: Role, **kwargs) -> Role:
        for key, value in kwargs.items():
            if value is not None:
                setattr(role, key, value)
        await self.db.flush()
        await self.db.refresh(role)
        return role

    async def deactivate(self, role: Role) -> Role:
        role.is_system = False  # mark as non-system so it can be managed
        await self.db.flush()
        return role


class PermissionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> list[Permission]:
        result = await self.db.execute(
            select(Permission).order_by(Permission.resource, Permission.action)
        )
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Permission | None:
        result = await self.db.execute(select(Permission).where(Permission.name == name))
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str, resource: str, action: str) -> Permission:
        perm = await self.get_by_name(name)
        if not perm:
            perm = Permission(name=name, resource=resource, action=action)
            self.db.add(perm)
            await self.db.flush()
            await self.db.refresh(perm)
        return perm


class RolePermissionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_role(self, role_id: str) -> list[RolePermission]:
        result = await self.db.execute(
            select(RolePermission)
            .where(RolePermission.role_id == role_id)
            .options(selectinload(RolePermission.permission))
        )
        return list(result.scalars().all())

    async def assign(self, role_id: str, permission_id: str) -> RolePermission:
        result = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        rp = RolePermission(role_id=role_id, permission_id=permission_id)
        self.db.add(rp)
        await self.db.flush()
        return rp

    async def revoke(self, role_id: str, permission_id: str) -> bool:
        result = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        rp = result.scalar_one_or_none()
        if not rp:
            return False
        await self.db.delete(rp)
        await self.db.flush()
        return True

    async def get_permission_by_id(self, permission_id: str) -> Permission | None:
        result = await self.db.execute(
            select(Permission).where(Permission.id == permission_id)
        )
        return result.scalar_one_or_none()


class UserRoleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_roles(self, user_id: str) -> list[UserRole]:
        result = await self.db.execute(
            select(UserRole)
            .where(UserRole.user_id == str(user_id))
            .options(selectinload(UserRole.role))
        )
        return list(result.scalars().all())

    async def get_role_names(self, user_id: str) -> list[str]:
        user_roles = await self.get_user_roles(str(user_id))
        return [ur.role.name for ur in user_roles]

    async def assign_role(self, user_id: str, role_id: str,
                          tenant_id: str | None, granted_by: str | None) -> UserRole:
        uid, rid = str(user_id), str(role_id)
        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == uid, UserRole.role_id == rid)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        ur = UserRole(
            user_id=uid,
            role_id=rid,
            tenant_id=str(tenant_id) if tenant_id else None,
            granted_by=str(granted_by) if granted_by else None,
        )
        self.db.add(ur)
        await self.db.flush()
        return ur

    async def get_by_user_and_role(self, user_id: str, role_id: str) -> UserRole | None:
        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == str(user_id), UserRole.role_id == str(role_id))
        )
        return result.scalar_one_or_none()

    async def get_users_by_role(self, role_id: str, limit: int = 50, offset: int = 0) -> list[UserRole]:
        result = await self.db.execute(
            select(UserRole)
            .where(UserRole.role_id == role_id, UserRole.is_active == True)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def deactivate_user_role(self, user_role: UserRole, reason: str) -> UserRole:
        user_role.is_active = False
        user_role.deactivated_at = datetime.now(timezone.utc)
        user_role.deactivated_reason = reason
        await self.db.flush()
        return user_role

    async def reactivate_user_role(self, user_role: UserRole) -> UserRole:
        user_role.is_active = True
        user_role.deactivated_at = None
        user_role.deactivated_reason = None
        await self.db.flush()
        return user_role

    async def list_by_role(self, role_id: str) -> list[UserRole]:
        result = await self.db.execute(
            select(UserRole)
            .where(UserRole.role_id == role_id)
            .options(selectinload(UserRole.role))
        )
        return list(result.scalars().all())

    async def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        result = await self.db.execute(
            select(UserRole)
            .where(UserRole.user_id == str(user_id))
            .options(
                selectinload(UserRole.role)
                .selectinload(Role.role_permissions)
                .selectinload(RolePermission.permission)
            )
        )
        user_roles = result.scalars().all()
        for ur in user_roles:
            for rp in ur.role.role_permissions:
                if rp.permission.resource == resource and rp.permission.action == action:
                    return True
        return False