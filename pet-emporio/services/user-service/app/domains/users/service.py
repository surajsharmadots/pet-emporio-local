import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.exceptions import AppException
from pe_common.logging import get_logger
from pe_common.events import EventPublisher

from .repository import UserRepository, AddressRepository, KycRepository
from .schemas import UserUpdate, AddressCreate, AddressUpdate, AdminUserUpdate, CompleteRegistrationRequest, WalkInCustomerCreate
from ..audit.repository import AuditRepository

logger = get_logger(__name__)


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)
        self.address_repo = AddressRepository(db)
        self.kyc_repo = KycRepository(db)
        self.audit_repo = AuditRepository(db)

    async def get_or_create_by_mobile(self, mobile: str, user_type: str = "customer"):
        user = await self.repo.get_by_mobile(mobile)
        if user:
            return user
        user = await self.repo.create(mobile=mobile, user_type=user_type, full_name="")
        logger.info("user_created", user_id=str(user.id), mobile=mobile[-4:] + "****")
        try:
            await EventPublisher.publish(
                event_type="user.registered",
                payload={"user_id": str(user.id), "mobile": mobile, "user_type": user_type},
                service="user-service",
            )
        except Exception as e:
            logger.warning("event_publish_failed", error=str(e))
        return user

    async def get_profile(self, user_id: uuid.UUID):
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise AppException(code="NOT_FOUND", message="User not found", status_code=404)
        return user

    async def update_profile(self, user_id: uuid.UUID, data: UserUpdate):
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise AppException(code="NOT_FOUND", message="User not found", status_code=404)

        update_data = data.model_dump(exclude_none=True)

        if "email" in update_data:
            existing = await self.repo.get_by_email(update_data["email"])
            if existing and existing.id != user_id:
                raise AppException(code="CONFLICT", message="Email already in use", status_code=409)

        user = await self.repo.update(user, **update_data)
        return user

    async def list_addresses(self, user_id: uuid.UUID):
        return await self.address_repo.get_by_user(user_id)

    async def add_address(self, user_id: uuid.UUID, data: AddressCreate):
        address_data = data.model_dump()
        return await self.address_repo.create(user_id, address_data)

    async def update_address(self, user_id: uuid.UUID, address_id: uuid.UUID, data: AddressUpdate):
        address = await self.address_repo.get_by_id(address_id)
        if not address or address.user_id != user_id:
            raise AppException(code="NOT_FOUND", message="Address not found", status_code=404)
        update_data = data.model_dump(exclude_none=True)
        return await self.address_repo.update(address, update_data)

    async def delete_address(self, user_id: uuid.UUID, address_id: uuid.UUID):
        address = await self.address_repo.get_by_id(address_id)
        if not address or address.user_id != user_id:
            raise AppException(code="NOT_FOUND", message="Address not found", status_code=404)
        await self.address_repo.delete(address)

    async def upload_kyc(self, user_id: uuid.UUID, doc_type: str, file_url: str):
        return await self.kyc_repo.create(user_id, doc_type, file_url)

    async def get_kyc_status(self, user_id: uuid.UUID):
        return await self.kyc_repo.get_by_user(user_id)

    # Admin operations
    async def admin_update_user(self, target_user_id: uuid.UUID, data: AdminUserUpdate,
                                actor_user_id: uuid.UUID):
        user = await self.repo.get_by_id(target_user_id)
        if not user:
            raise AppException(code="NOT_FOUND", message="User not found", status_code=404)

        old_values = {"is_active": user.is_active}
        update_data = data.model_dump(exclude_none=True)
        user = await self.repo.update(user, **update_data)

        await self.audit_repo.log(
            user_id=actor_user_id,
            action="admin.user.update",
            resource_type="user",
            resource_id=target_user_id,
            old_values=old_values,
            new_values=update_data,
        )
        return user

    async def approve_kyc(self, kyc_id: uuid.UUID, reviewer_id: uuid.UUID):
        kyc = await self.kyc_repo.get_by_id(kyc_id)
        if not kyc:
            raise AppException(code="NOT_FOUND", message="KYC document not found", status_code=404)
        kyc = await self.kyc_repo.update_status(kyc, "approved", reviewer_id)
        await self.audit_repo.log(
            user_id=reviewer_id,
            action="admin.kyc.approve",
            resource_type="kyc_document",
            resource_id=kyc_id,
        )
        try:
            await EventPublisher.publish(
                event_type="user.kyc_verified",
                payload={"user_id": str(kyc.user_id), "kyc_id": str(kyc_id), "doc_type": kyc.doc_type},
                service="user-service",
            )
        except Exception as e:
            logger.warning("event_publish_failed", error=str(e))
        return kyc

    async def complete_registration(self, user_id: uuid.UUID, data: CompleteRegistrationRequest):
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise AppException(code="NOT_FOUND", message="User not found", status_code=404)

        if user.first_name:
            raise AppException(code="CONFLICT", message="Registration already completed", status_code=409)

        existing = await self.repo.get_by_email(data.email)
        if existing and existing.id != user_id:
            raise AppException(code="CONFLICT", message="Email already in use", status_code=409)

        user = await self.repo.update(
            user,
            first_name=data.first_name,
            last_name=data.last_name,
            full_name=f"{data.first_name} {data.last_name}",
            email=data.email,
            is_profile_complete=True,
        )
        return user

    async def create_walk_in_customer(self, provider_tenant_id: str, data: WalkInCustomerCreate):
        existing = await self.repo.get_by_mobile(data.mobile)
        if existing:
            raise AppException(code="CONFLICT", message="User with this mobile already exists", status_code=409)

        user = await self.repo.create(
            mobile=data.mobile,
            user_type="customer",
            full_name=f"{data.first_name} {data.last_name}",
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            is_walk_in=True,
            created_by_provider_id=provider_tenant_id,
        )
        return user

    async def list_walk_in_customers(self, provider_tenant_id: str, limit: int = 20, offset: int = 0):
        return await self.repo.list_walk_in_by_provider(provider_tenant_id, limit=limit, offset=offset)

    async def reject_kyc(self, kyc_id: uuid.UUID, reviewer_id: uuid.UUID, reason: str):
        kyc = await self.kyc_repo.get_by_id(kyc_id)
        if not kyc:
            raise AppException(code="NOT_FOUND", message="KYC document not found", status_code=404)
        kyc = await self.kyc_repo.update_status(kyc, "rejected", reviewer_id, rejection_reason=reason)
        await self.audit_repo.log(
            user_id=reviewer_id,
            action="admin.kyc.reject",
            resource_type="kyc_document",
            resource_id=kyc_id,
            new_values={"rejection_reason": reason},
        )
        return kyc