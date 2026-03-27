import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Date, Numeric, DateTime, Text
from sqlalchemy.orm import relationship

from ...database import Base


def _uuid():
    return str(uuid.uuid4())


class CommissionConfig(Base):
    __tablename__ = "commission_configs"

    id = Column(String(36), primary_key=True, default=_uuid)
    # 'platform', 'tenant_type', 'tenant'
    scope = Column(String(20), nullable=False)
    # 'seller', 'doctor', 'lab', 'groomer', 'pharmacy' — used when scope='tenant_type'
    tenant_type = Column(String(30), nullable=True)
    # specific tenant override — used when scope='tenant'
    tenant_id = Column(String(36), nullable=True)
    # 'percentage' or 'flat'
    commission_type = Column(String(10), nullable=False, default="percentage")
    commission_value = Column(Numeric(5, 2), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))