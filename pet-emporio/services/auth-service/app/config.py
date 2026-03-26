from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SERVICE_NAME: str = "auth-service"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/pe_auth"
    REDIS_URL: str = "redis://localhost:6380/0"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    OTP_EXPIRE_SECONDS: int = 3000       # 5 minutes
    OTP_RATE_LIMIT: int = 30             # max OTP requests
    OTP_RATE_WINDOW_SECONDS: int = 600  # per 10 minutes

    DEV_MODE: bool = True               # if True: log OTP to terminal, skip real SMS
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""         # MSG91 OTP template ID from dashboard
    MSG91_SENDER_ID: str = "PETEMP"     # 6-char sender ID registered with MSG91
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    FACEBOOK_APP_ID: str = ""           # Optional: for token validation via app-level debug_token
    APPLE_BUNDLE_ID: str = ""           # e.g. "com.petemporio.app" — audience claim in Apple JWT
    USER_SERVICE_URL: str = "http://localhost:8012"

    # Keycloak — auth-service verifies OTP/social tokens, syncs user into KC and fetches real roles
    KEYCLOAK_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "pet-emporio"
    KEYCLOAK_CLIENT_ID: str = "auth-service"
    KEYCLOAK_CLIENT_SECRET: str = "auth-service-secret"
    KEYCLOAK_ADMIN_USER: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = "admin"
    KEYCLOAK_ENABLED: bool = False

    # Comma-separated list of allowed CORS origins.
    # Dev default allows local frontend dev servers.
    # Production: set to your actual domains e.g. "https://petemporio.com,https://admin.petemporio.com"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:5173"

    # Device binding
    DEVICE_CHALLENGE_TTL_SECONDS: int = 300

    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://jaeger:4317"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()