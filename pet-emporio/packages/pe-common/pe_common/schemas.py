from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    meta: dict = Field(default_factory=lambda: {
        "request_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat()
    })


def success_response(data: Any, meta: dict = None) -> dict:
    return ApiResponse(success=True, data=data, meta=meta or {
        "request_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat()
    }).model_dump()


def paginated_response(data: list, page: int, page_size: int, total: int) -> dict:
    return {
        "success": True,
        "data": data,
        "meta": {
            "request_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size
            }
        }
    }
