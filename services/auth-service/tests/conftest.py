import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fakeredis.aioredis import FakeRedis
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from app.main import app
from app.database import Base, get_db
from app.redis_client import get_redis

def _gen_rsa_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem

TEST_PRIVATE_KEY, TEST_PUBLIC_KEY = _gen_rsa_keys()

@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "JWT_PRIVATE_KEY", TEST_PRIVATE_KEY)
    monkeypatch.setattr(config.settings, "JWT_PUBLIC_KEY", TEST_PUBLIC_KEY)
    monkeypatch.setattr(config.settings, "DEV_MODE", True)
    # Disable Keycloak so tests use self-signed JWTs and local session storage only
    monkeypatch.setattr(config.settings, "KEYCLOAK_ENABLED", False)
    # pe_common.auth reads PUBLIC_KEY at module import time — patch it too
    import pe_common.auth as pe_auth
    monkeypatch.setattr(pe_auth, "PUBLIC_KEY", TEST_PUBLIC_KEY)

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