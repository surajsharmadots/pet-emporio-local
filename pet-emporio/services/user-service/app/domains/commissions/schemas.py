import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Literal
from pydantic import BaseModel, Field


class CommissionConfigCreate(BaseModel):
    scope: Literal["platform", "tenant_type", "tenant"]
    tenant_type: Optional[str] = None
    tenant_id: Optional[uuid.UUID] = None
    commission_type: Literal["percentage", "flat"] = "percentage"
    commission_value: Decimal = Field(..., ge=0, le=100)
    effective_from: date
    effective_to: Optional[date] = None


class CommissionConfigUpdate(BaseModel):
    commission_type: Optional[Literal["percentage", "flat"]] = None
    commission_value: Optional[Decimal] = Field(None, ge=0, le=100)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class CommissionConfigResponse(BaseModel):
    id: uuid.UUID
    scope: str
    tenant_type: Optional[str] = None
    tenant_id: Optional[uuid.UUID] = None
    commission_type: str
    commission_value: Decimal
    effective_from: date
    effective_to: Optional[date] = None
    created_by: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ResolvedCommissionResponse(BaseModel):
    commission_type: str
    commission_value: Decimal
    scope: str