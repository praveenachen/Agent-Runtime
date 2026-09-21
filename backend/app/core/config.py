from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agent Runtime"
    environment: str = "development"
    demo_mode: bool = False
    database_url: str = "sqlite:///./agent_runtime.db"
    redis_url: str = "redis://redis:6379/0"
    queue_name: str = "agent-runtime"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    provider_timeout_seconds: float = Field(default=60, gt=0, le=300)
    retry_base_seconds: int = Field(default=5, ge=1, le=300)
    retry_max_seconds: int = Field(default=60, ge=1, le=3600)
    dispatch_interval_seconds: int = Field(default=2, ge=1, le=60)
    redispatch_seconds: int = Field(default=30, ge=5, le=300)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def demo_enabled(self) -> bool:
        return self.demo_mode and self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
