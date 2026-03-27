import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from ...enums import TenantType, TenantStatus


class TenantRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, strip_whitespace=True)
    tenant_type: TenantType
    business_name: str = Field(..., min_length=2, max_length=255, strip_whitespace=True)
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255, strip_whitespace=True)
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    business_address: Optional[dict] = None
    bank_details: Optional[dict] = None


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    tenant_type: TenantType
    status: TenantStatus
    owner_user_id: uuid.UUID
    commission_rate: float
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TenantRejectRequest(BaseModel):
    reason: str = Field(..., min_length=5, strip_whitespace=True)