import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, ForeignKey, Numeric, DateTime, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship

from ...database import Base
from ...enums import TenantType, TenantStatus, TenantPlan


def _uuid():
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_type = Column(SAEnum(TenantType, native_enum=False, length=50), nullable=False)
    plan = Column(SAEnum(TenantPlan, native_enum=False, length=50), nullable=False, default=TenantPlan.basic)
    status = Column(SAEnum(TenantStatus, native_enum=False, length=20), nullable=False, default=TenantStatus.pending)
    commission_rate = Column(Numeric(5, 2), nullable=False, default=10.00)
    logo_url = Column(Text, nullable=True)
    gst_number = Column(String(20), nullable=True)
    pan_number = Column(String(20), nullable=True)
    business_address = Column(JSON, nullable=True)
    bank_details = Column(JSON, nullable=True)
    settings = Column(JSON, nullable=False, default=dict)
    rejection_reason = Column(Text, nullable=True)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", foreign_keys=[owner_user_id])
    approver = relationship("User", foreign_keys=[approved_by])