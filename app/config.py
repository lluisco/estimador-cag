from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PRIMARY_MODEL: str = "openai/gpt-4o-mini"
    FALLBACK_MODEL: str = "anthropic/claude-haiku-4-5-20251001"
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_NUM_RETRIES: int = 1
    # Tope de tokens de salida de /estimate. La salida estructurada (fases + supuestos) es larga.
    ESTIMATION_MAX_TOKENS: int = 4000

    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 86400  # 24h

    # EUR/hora por rol. "other" se aplica a cualquier rol no listado.
    HOURLY_RATES_EUR: dict[str, int] = {
        "developer": 60,
        "project_manager": 60,
        "ux_ui": 50,
        "other": 50,
    }

    APP_ENV: str = "development"
    LOG_LEVEL: str = "info"

    SESSION_MAX_TURNS: int = 6
    # Tope de caracteres por adjunto: protege el presupuesto del prompt (el chunking llega con RAG).
    MAX_ATTACHMENT_CHARS: int = 60_000
    # Modelo de la segunda llamada por turno (extractor de project_metadata).
    METADATA_EXTRACTOR_MODEL: str = "openai/gpt-4o-mini"

    # Modelo utilizado para la compresión de conversaciones.
    COMPRESSION_MODEL: str = "openai/gpt-4o-mini"

    # Modelo del Critic (auditor de la estimación en el flujo ACB).
    CRITIC_MODEL: str = "openai/gpt-4o-mini"
    # Iteraciones máximas del bucle ACB (cada una: 1 llamada al actor + 1 al critic).
    BOSS_MAX_ITERATIONS: int = 3


settings = Settings()