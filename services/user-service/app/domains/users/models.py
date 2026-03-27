import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Text, Date, ForeignKey, Numeric, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship

from ...database import Base
from ...enums import UserType, Gender, KycDocType, KycStatus, OnboardingStatus, PortalType


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    auth_user_id = Column(String(36), unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    mobile = Column(String(20), unique=True, nullable=True)
    full_name = Column(String(255), nullable=False, default="")
    avatar_url = Column(Text, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(SAEnum(Gender, native_enum=False, length=20), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    is_profile_complete = Column(Boolean, nullable=False, default=False)
    is_walk_in = Column(Boolean, nullable=False, default=False)
    created_by_provider_id = Column(String(36), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    tenant_id = Column(String(36), nullable=True)
    user_type = Column(SAEnum(UserType, native_enum=False, length=50), nullable=False, default=UserType.customer)
    fcm_token = Column(Text, nullable=True)
    web_push_token = Column(Text, nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    addresses = relationship("UserAddress", back_populates="user", cascade="all, delete-orphan")
    kyc_documents = relationship("KycDocument", back_populates="user")
    user_roles = relationship("UserRole", back_populates="user", foreign_keys="UserRole.user_id")


class UserAddress(Base):
    __tablename__ = "user_addresses"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(100), default="Home")
    full_name = Column(String(255), nullable=False, default="")
    mobile = Column(String(20), nullable=True)
    address_line_1 = Column(Text, nullable=False)
    address_line_2 = Column(Text, nullable=True)
    landmark = Column(Text, nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    pincode = Column(String(10), nullable=False)
    country = Column(String(100), nullable=False, default="India")
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="addresses")


class KycDocument(Base):
    __tablename__ = "kyc_documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    doc_type = Column(SAEnum(KycDocType, native_enum=False, length=50), nullable=False)
    file_url = Column(Text, nullable=False)
    status = Column(SAEnum(KycStatus, native_enum=False, length=20), nullable=False, default=KycStatus.pending)
    reviewed_by = Column(String(36), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="kyc_documents")


class OnboardingRequest(Base):
    """
    Stores provider self-registration requests that are awaiting admin review.
    A user account is NOT created until the admin approves the request.
    On approval, the service layer creates the user, tenant, and assigns the role.
    """
    __tablename__ = "onboarding_requests"

    id = Column(String(36), primary_key=True, default=_uuid)
    portal_type = Column(SAEnum(PortalType, native_enum=False, length=30), nullable=False)
    mobile = Column(String(20), nullable=False)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    business_name = Column(String(255), nullable=True)   # seller and pharmacy only
    location = Column(Text, nullable=True)               # doctor, lab, groomer
    status = Column(
        SAEnum(OnboardingStatus, native_enum=False, length=20),
        nullable=False,
        default=OnboardingStatus.pending,
    )
    rejection_reason = Column(Text, nullable=True)
    reviewed_by = Column(String(36), nullable=True)      # admin user_id
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    user_id = Column(String(36), nullable=True)          # set after approval
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))