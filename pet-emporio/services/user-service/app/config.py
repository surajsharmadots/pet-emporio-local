from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SERVICE_NAME: str = "user-service"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/pe_users"
    REDIS_URL: str = "redis://localhost:6380/0"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    JWT_PUBLIC_KEY: str = ""
    JWT_ALGORITHM: str = "RS256"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_USERS: str = "pe-users"
    MINIO_SECURE: bool = False

    AUTH_SERVICE_URL: str = "http://auth-service:8000"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://jaeger:4317"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:5173"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()