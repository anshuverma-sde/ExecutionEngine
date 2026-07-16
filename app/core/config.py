from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@postgres:5432/engine"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # DhanHQ
    DHAN_CLIENT_ID: str = ""
    DHAN_ACCESS_TOKEN: str = ""

    # AI (Groq — OpenAI-compatible, free tier)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Notification
    WEBHOOK_URL: str = "http://webhook-mock:8001/notify"
    WEBHOOK_TIMEOUT_SECONDS: int = 10

    # App
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


settings = Settings()
