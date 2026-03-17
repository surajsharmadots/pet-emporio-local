from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": exc.code, "message": exc.message, "details": exc.details}
        }
    )


class NotFoundError(AppException):
    def __init__(self, resource: str, resource_id: str = None):
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} not found" + (f": {resource_id}" if resource_id else ""),
            status_code=404
        )


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401)


class ForbiddenError(AppException):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(code="FORBIDDEN", message=message, status_code=403)


class ValidationError(AppException):
    def __init__(self, message: str, details: dict = None):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422, details=details or {})


class ConflictError(AppException):
    def __init__(self, message: str):
        super().__init__(code="CONFLICT", message=message, status_code=409)