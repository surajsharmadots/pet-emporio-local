import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fakeredis.aioredis import FakeRedis

from app.main import app
from app.database import Base, get_db
from app.redis_client import get_redis

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()

@pytest_asyncio.fixture
async def fake_redis():
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()

@pytest_asyncio.fixture
async def client(db_session, fake_redis):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: fake_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()

def auth_headers(user_id: str, roles: list[str] | None = None, tenant_id: str | None = None) -> dict:
    """Build X-User-Id / X-User-Roles headers (simulates Kong JWT injection)."""
    headers = {"X-User-Id": user_id}
    if roles:
        headers["X-User-Roles"] = ",".join(roles)
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    return headers

@pytest.fixture
def customer_id() -> str:
    return str(uuid.uuid4())

@pytest.fixture
def admin_id() -> str:
    return str(uuid.uuid4())

@pytest.fixture
def customer_headers(customer_id) -> dict:
    return auth_headers(customer_id, roles=["customer"])

@pytest.fixture
def admin_headers(admin_id) -> dict:
    return auth_headers(admin_id, roles=["super_admin"])

async def create_user_in_db(db: AsyncSession, mobile: str = "+919876543210",
                             user_type: str = "customer") -> dict:
    """Insert a user directly into the test DB and return its data."""
    from app.domains.users.repository import UserRepository
    repo = UserRepository(db)
    user = await repo.create(mobile=mobile, user_type=user_type, full_name="Test User")
    await db.commit()
    return user