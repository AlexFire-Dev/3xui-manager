from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://manager:manager@localhost:5432/manager"
    public_base_url: str = "http://localhost:8000"

    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("admin")
    jwt_secret: SecretStr = SecretStr("change-me-in-production")
    admin_token_ttl_seconds: int = 60 * 60 * 12

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


settings = Settings()
