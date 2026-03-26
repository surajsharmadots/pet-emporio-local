from contextlib import asynccontextmanager
from fastapi import FastAPI

from pe_common.exceptions import AppException, app_exception_handler
from pe_common.logging import setup_logging

from .config import settings
from .redis_client import close_redis
from .domains.users.router import router as users_router
from .domains.tenants.router import router as tenants_router
from .domains.rbac.router import router as rbac_router
from .domains.commissions.router import router as commissions_router, internal_router as commissions_internal_router
from .routers.internal import router as internal_router
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.SERVICE_NAME)

    # Seed system roles (best-effort — don't block startup on failure)
    try:
        from .database import AsyncSessionLocal
        from .domains.rbac.service import RbacService
        async with AsyncSessionLocal() as db:
            svc = RbacService(db)
            await svc.seed_roles()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"RBAC seed failed (non-fatal): {e}")

    # Start RabbitMQ event consumer (best-effort)
    _consumer_connection = None
    try:
        from .consumers.event_consumer import start_consumer
        _consumer_connection = await start_consumer()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Event consumer failed to start (non-fatal): {e}")

    yield

    if _consumer_connection:
        try:
            await _consumer_connection.close()
        except Exception:
            pass
    await close_redis()


app = FastAPI(
    title="User Service",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-User-Id", "X-User-Roles", "X-Tenant-Id"],
)


app.add_exception_handler(AppException, app_exception_handler)

app.include_router(users_router)
app.include_router(tenants_router)
app.include_router(rbac_router)
app.include_router(commissions_router)
app.include_router(commissions_internal_router)
app.include_router(internal_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/ready")
async def ready():
    return {"status": "ready"}