from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

OPENROUTER_MODEL = "qwen/qwen3.5-9b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openrouter_api_key: str = ""
    # The assignment requires the model name to be declared in source code.
    openrouter_model: str = OPENROUTER_MODEL
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    database_url: str = "postgresql://olist:change-me@localhost:5432/olist_disputes"
    postgres_db: str = "olist_disputes"
    postgres_user: str = "olist"
    postgres_password: str = "change-me"

    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    data_dir: Path = Path("data")
    input_dir: Path = Path("input")
    output_dir: Path = Path("output")
    logging_dir: Path = Path("logging")

    @property
    def langfuse_configured(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key)


def get_settings() -> Settings:
    return Settings()
