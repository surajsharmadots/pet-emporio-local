from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from sqlalchemy import select, update, func
import uuid
from .models import User, UserAddress, KycDocument, OnboardingRequest


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.id == user_id,
                User.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_mobile(self, mobile: str) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.mobile == mobile,
                User.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.email == email,
                User.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def create_social(self, email: str | None, full_name: str = "") -> User:
        user = User(
            mobile=None,
            user_type="customer",
            email=email,
            full_name=full_name
        )
        self.db.add(user)
        await self.db.commit() 
        await self.db.refresh(user)
        return user

    async def create(self, mobile: str, user_type: str = "customer", **kwargs) -> User:
        user = User(
            mobile=mobile,
            user_type=user_type,
            **kwargs
        )
        self.db.add(user)
        await self.db.commit() 
        await self.db.refresh(user)
        return user

    async def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            if value is not None:
                setattr(user, key, value)

        self.db.add(user)             
        await self.db.commit() 
        await self.db.refresh(user) 
        return user

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[User]:
        result = await self.db.execute(
            select(User)
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_all(self) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None))
        )
        return result.scalar_one()

    async def list_walk_in_by_provider(
        self,
        provider_tenant_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> list[User]:
        result = await self.db.execute(
            select(User)
            .where(
                User.created_by_provider_id == provider_tenant_id,
                User.deleted_at.is_(None)
            )
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

class AddressRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user(self, user_id: str) -> list[UserAddress]:
        result = await self.db.execute(
            select(UserAddress)
            .where(UserAddress.user_id == str(user_id))
            .order_by(UserAddress.is_default.desc(), UserAddress.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, address_id: str) -> UserAddress | None:
        result = await self.db.execute(
            select(UserAddress).where(UserAddress.id == str(address_id))
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: str, data: dict) -> UserAddress:
        if data.get("is_default"):
            await self._clear_default(str(user_id))
        address = UserAddress(user_id=str(user_id), **data)
        self.db.add(address)
        await self.db.flush()
        await self.db.refresh(address)
        return address

    async def update(self, address: UserAddress, data: dict) -> UserAddress:
        if data.get("is_default"):
            await self._clear_default(address.user_id)
        for key, value in data.items():
            if value is not None:
                setattr(address, key, value)
        await self.db.flush()
        await self.db.refresh(address)
        return address

    async def delete(self, address: UserAddress) -> None:
        await self.db.delete(address)
        await self.db.flush()

    async def _clear_default(self, user_id: str) -> None:
        await self.db.execute(
            update(UserAddress)
            .where(UserAddress.user_id == user_id)
            .values(is_default=False)
        )


class KycRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user(self, user_id: str) -> list[KycDocument]:
        result = await self.db.execute(
            select(KycDocument).where(KycDocument.user_id == str(user_id))
        )
        return list(result.scalars().all())

    async def get_by_id(self, kyc_id: str) -> KycDocument | None:
        result = await self.db.execute(
            select(KycDocument).where(KycDocument.id == str(kyc_id))
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: str, doc_type: str, file_url: str) -> KycDocument:
        doc = KycDocument(user_id=str(user_id), doc_type=doc_type, file_url=file_url)
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)
        return doc

    async def list_pending(self) -> list[KycDocument]:
        result = await self.db.execute(
            select(KycDocument).where(KycDocument.status == "pending")
        )
        return list(result.scalars().all())

    async def update_status(self, kyc: KycDocument, status: str, reviewed_by: str,
                            rejection_reason: str | None = None) -> KycDocument:
        kyc.status = status
        kyc.reviewed_by = str(reviewed_by)
        kyc.reviewed_at = datetime.now(timezone.utc)
        if rejection_reason:
            kyc.rejection_reason = rejection_reason
        await self.db.flush()
        await self.db.refresh(kyc)
        return kyc


class OnboardingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> OnboardingRequest:
        req = OnboardingRequest(**data)
        self.db.add(req)
        await self.db.flush()
        await self.db.refresh(req)
        return req

    async def get_by_id(self, request_id: str) -> OnboardingRequest | None:
        result = await self.db.execute(
            select(OnboardingRequest).where(OnboardingRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_by_mobile(self, mobile: str) -> OnboardingRequest | None:
        """Returns the most recent pending or approved request for a mobile number."""
        result = await self.db.execute(
            select(OnboardingRequest)
            .where(
                OnboardingRequest.mobile == mobile,
                OnboardingRequest.status.in_(["pending", "approved"]),
            )
            .order_by(OnboardingRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_status(
        self, status: str, limit: int = 50, offset: int = 0
    ) -> list[OnboardingRequest]:
        result = await self.db.execute(
            select(OnboardingRequest)
            .where(OnboardingRequest.status == status)
            .order_by(OnboardingRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_status(self, status: str) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(OnboardingRequest)
            .where(OnboardingRequest.status == status)
        )
        return result.scalar_one()

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[OnboardingRequest]:
        result = await self.db.execute(
            select(OnboardingRequest)
            .order_by(OnboardingRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_all(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(OnboardingRequest))
        return result.scalar_one()

    async def approve(
        self, req: OnboardingRequest, reviewer_id: str, user_id: str
    ) -> OnboardingRequest:
        req.status = "approved"
        req.reviewed_by = reviewer_id
        req.reviewed_at = datetime.now(timezone.utc)
        req.user_id = user_id
        await self.db.flush()
        await self.db.refresh(req)
        return req

    async def reject(
        self, req: OnboardingRequest, reviewer_id: str, reason: str
    ) -> OnboardingRequest:
        req.status = "rejected"
        req.reviewed_by = reviewer_id
        req.reviewed_at = datetime.now(timezone.utc)
        req.rejection_reason = reason
        await self.db.flush()
        await self.db.refresh(req)
        return req