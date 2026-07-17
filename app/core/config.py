from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL — set either DATABASE_URL directly, or the individual DB_* vars.
    # If DATABASE_URL is not set, it is composed from DB_HOST/PORT/USER/PASSWORD/NAME.
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "engine"
    DATABASE_URL: str = ""  # overrides DB_* vars when set explicitly

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # DhanHQ
    DHAN_CLIENT_ID: str = ""
    DHAN_ACCESS_TOKEN: str = ""

    # AI — provider-agnostic (set LLM_PROVIDER to switch)
    # Supported: groq | openai | ollama | langchain
    LLM_PROVIDER: str = "groq"
    # LangChain backend — only used when LLM_PROVIDER=langchain
    # Supported: groq | openai
    LANGCHAIN_BACKEND: str = "groq"

    # Groq (free tier) — https://console.groq.com
    # Best for tool use (2026): groq/compound, openai/gpt-oss-120b
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "groq/compound"

    # OpenAI — https://platform.openai.com
    # Latest flagship (2026): gpt-5.6 | cost-balanced: gpt-5.6-terra
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.6-terra"

    # Ollama (local, no API key needed) — https://ollama.com
    # Best local tool-caller (2026): qwen3:8b (5GB), qwen3:14b (9GB)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"

    # Notification
    WEBHOOK_URL: str = "http://localhost:8001/notify"
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    # Circuit breaker: fail-fast after this many consecutive webhook failures
    WEBHOOK_CIRCUIT_BREAKER_THRESHOLD: int = 5
    # Circuit breaker: seconds before auto-reset after tripping
    WEBHOOK_CIRCUIT_BREAKER_RESET_SECONDS: int = 60

    # Celery notification task — tunable per environment
    NOTIFICATION_MAX_RETRIES: int = 5       # max delivery attempts (0 = first try only)
    NOTIFICATION_BACKOFF_BASE_SECONDS: int = 30  # doubles each attempt: 30→60→120→240→480

    # App
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    @property
    def database_url(self) -> str:
        """Return DATABASE_URL if set explicitly, else compose from DB_* vars."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def sync_database_url(self) -> str:
        """psycopg2 URL for Celery sync tasks."""
        return self.database_url.replace("+asyncpg", "+psycopg2")


settings = Settings()
