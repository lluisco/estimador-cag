from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "claude-haiku-4-5"

    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""


settings = Settings()