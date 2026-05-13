from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: SecretStr = Field(alias="TELEGRAM_BOT_TOKEN")
    api_base_url: str = Field(default="http://localhost:8000", alias="BOT_API_BASE_URL")
    public_sub_base_url: str = Field(default="http://localhost:8000", alias="BOT_PUBLIC_SUB_BASE_URL")
    admin_username: str = Field(default="admin", alias="BOT_ADMIN_USERNAME")
    admin_password: SecretStr = Field(default=SecretStr("admin"), alias="BOT_ADMIN_PASSWORD")
    request_timeout_seconds: float = Field(default=30.0, alias="BOT_REQUEST_TIMEOUT_SECONDS")
    traffic_refresh: bool = Field(default=True, alias="BOT_TRAFFIC_REFRESH")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("api_base_url", "public_sub_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


settings = Settings()
