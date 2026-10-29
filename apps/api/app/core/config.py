from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: SecretStr
    database_timeout_seconds: float = Field(default=3, gt=0, le=10)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    github_token: SecretStr | None = None
    sync_enabled: bool = False
    sync_interval_hours: int = Field(default=24, ge=1, le=168)
    sync_max_records: int = Field(default=1500, ge=1, le=10000)
    sync_readme_limit: int = Field(default=30, ge=0, le=200)
    sync_mcp_limit: int = Field(default=100, ge=1, le=10000)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
            valid = url.drivername == "postgresql+psycopg" and bool(url.host and url.database)
        except ArgumentError:
            valid = False
        if not valid:
            raise ValueError("DATABASE_URL 必须是有效的 postgresql+psycopg 连接地址")
        return value
