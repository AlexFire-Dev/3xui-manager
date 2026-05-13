from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://manager:manager@localhost:5432/manager"
    public_base_url: str = "http://localhost:8000"

    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("admin")
    jwt_secret: SecretStr = SecretStr("change-me-in-production")
    admin_token_ttl_seconds: int = 60 * 60 * 12


    maintenance_run_hour_utc: int = 3
    maintenance_run_minute_utc: int = 0
    maintenance_loop_sleep_seconds: int = 60
    maintenance_run_on_start: bool = False

    maintenance_daily_snapshot_enabled: bool = True

    maintenance_cleanup_missing_enabled: bool = True
    maintenance_missing_remote_config_grace_hours: int = 24

    maintenance_reset_traffic_enabled: bool = True
    maintenance_reset_traffic_mode: str = "clients"

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


settings = Settings()
