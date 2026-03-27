import uuid
from typing import Optional
from pydantic import BaseModel


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: Optional[str] = None
    is_system: bool

    model_config = {"from_attributes": True}


class PermissionResponse(BaseModel):
    id: uuid.UUID
    name: str
    resource: str
    action: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class RoleAssignRequest(BaseModel):
    role_name: str
    tenant_id: Optional[uuid.UUID] = None


class PermissionCheckRequest(BaseModel):
    resource: str
    action: str


class RoleCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None


class RolePermissionAssign(BaseModel):
    permission_id: uuid.UUID


class SubAdminCreate(BaseModel):
    mobile: str
    email: Optional[str] = None
    first_name: str
    last_name: str
    role_id: uuid.UUID


class SubAdminUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    role_id: Optional[uuid.UUID] = None


class SubAdminDeactivate(BaseModel):
    reason: str