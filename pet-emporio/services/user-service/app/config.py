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

    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://jaeger:4317"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()