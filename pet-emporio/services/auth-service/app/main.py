from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from pe_common.exceptions import AppException, app_exception_handler
from pe_common.logging import setup_logging

from .config import settings
from .database import create_tables
from .redis_client import close_redis
from .routers.auth import router as auth_router
from .routers.internal import router as internal_router
from .routers.admin import router as admin_router
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.SERVICE_NAME)
    await create_tables()
    yield
    await close_redis()


app = FastAPI(
    title="Auth Service",
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

app.include_router(auth_router)
app.include_router(internal_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/ready")
async def ready():
    return {"status": "ready"}