from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pe_common.schemas import success_response
from pe_common.auth import get_current_user
from pe_common.exceptions import AppException

from ...database import get_db
from .schemas import CommissionConfigCreate, CommissionConfigUpdate, CommissionConfigResponse, ResolvedCommissionResponse
from .repository import CommissionRepository

router = APIRouter(tags=["commissions"])
internal_router = APIRouter(tags=["commissions-internal"])


def _require_admin(current_user: dict):
    roles = current_user.get("roles", [])
    if not any(r in roles for r in ("super_admin", "admin")):
        raise AppException(code="PERMISSION_DENIED", message="Admin access required", status_code=403)


# ─── Admin Commission Management ─────────────────────────────────────────────

@router.get("/api/v1/admin/commissions")
async def list_commissions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    repo = CommissionRepository(db)
    configs = await repo.list_all()
    return success_response([CommissionConfigResponse.model_validate(c).model_dump() for c in configs])


@router.post("/api/v1/admin/commissions")
async def create_commission(
    body: CommissionConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    repo = CommissionRepository(db)
    data = body.model_dump(exclude_none=True)
    data["created_by"] = current_user["user_id"]
    if "tenant_id" in data and data["tenant_id"]:
        data["tenant_id"] = str(data["tenant_id"])
    config = await repo.create(**data)
    await db.commit()
    return success_response(CommissionConfigResponse.model_validate(config).model_dump())


@router.patch("/api/v1/admin/commissions/{config_id}")
async def update_commission(
    config_id: str,
    body: CommissionConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    repo = CommissionRepository(db)
    config = await repo.get_by_id(config_id)
    if not config:
        raise AppException(code="NOT_FOUND", message="Commission config not found", status_code=404)
    update_data = body.model_dump(exclude_none=True)
    config = await repo.update(config, **update_data)
    await db.commit()
    return success_response(CommissionConfigResponse.model_validate(config).model_dump())


@router.get("/api/v1/admin/commissions/history")
async def commission_history(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    repo = CommissionRepository(db)
    configs = await repo.list_all()
    return success_response([CommissionConfigResponse.model_validate(c).model_dump() for c in configs])


# ─── Internal: Resolve Commission for a Tenant ───────────────────────────────

@internal_router.get("/internal/v1/commissions")
async def resolve_commission(
    tenant_id: str = Query(...),
    tenant_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    repo = CommissionRepository(db)
    config = await repo.resolve_for_tenant(tenant_id, tenant_type)
    if not config:
        # Default fallback: 10% platform commission
        return success_response(
            ResolvedCommissionResponse(
                commission_type="percentage",
                commission_value=10,
                scope="default",
            ).model_dump()
        )
    return success_response(
        ResolvedCommissionResponse(
            commission_type=config.commission_type,
            commission_value=config.commission_value,
            scope=config.scope,
        ).model_dump()
    )