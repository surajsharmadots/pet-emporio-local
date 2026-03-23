import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

from ...enums import UserType, Gender, KycDocType, KycStatus


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255, strip_whitespace=True)
    email: Optional[EmailStr] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    fcm_token: Optional[str] = None
    web_push_token: Optional[str] = None


class CompleteRegistrationRequest(BaseModel):
    first_name: str = Field(..., max_length=100, strip_whitespace=True)
    last_name: str = Field(..., max_length=100, strip_whitespace=True)
    email: EmailStr


class WalkInCustomerCreate(BaseModel):
    first_name: str = Field(..., max_length=100, strip_whitespace=True)
    last_name: str = Field(..., max_length=100, strip_whitespace=True)
    mobile: str = Field(..., max_length=20)
    email: Optional[EmailStr] = None


class WalkInCustomerResponse(BaseModel):
    user_id: str
    first_name: Optional[str]
    last_name: Optional[str]
    mobile: str


class UserResponse(BaseModel):
    id: uuid.UUID
    mobile: str
    email: Optional[str] = None
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_profile_complete: bool = False
    avatar_url: Optional[str] = None
    user_type: UserType
    is_active: bool
    is_verified: bool
    tenant_id: Optional[uuid.UUID] = None
    roles: list[str] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AddressCreate(BaseModel):
    label: Optional[str] = Field(None, max_length=100)
    full_name: str = Field(..., max_length=255, strip_whitespace=True)
    mobile: Optional[str] = None
    address_line_1: str = Field(..., strip_whitespace=True)
    address_line_2: Optional[str] = None
    landmark: Optional[str] = None
    city: str = Field(..., strip_whitespace=True)
    state: str = Field(..., strip_whitespace=True)
    pincode: str = Field(..., pattern=r"^\d{6}$")
    country: str = "India"
    is_default: bool = False


class AddressUpdate(BaseModel):
    label: Optional[str] = None
    full_name: Optional[str] = None
    mobile: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    landmark: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = Field(None, pattern=r"^\d{6}$")
    is_default: Optional[bool] = None


class AddressResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    label: Optional[str] = None
    full_name: str
    mobile: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    landmark: Optional[str] = None
    city: str
    state: str
    pincode: str
    country: str
    is_default: bool

    model_config = {"from_attributes": True}


class KycUploadRequest(BaseModel):
    doc_type: KycDocType
    file_url: str  # MinIO URL (uploaded by client directly or via /media/upload)


class KycDocumentResponse(BaseModel):
    id: uuid.UUID
    doc_type: str
    file_url: str
    status: KycStatus
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# Admin
class AdminUserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    user_type: Optional[UserType] = None