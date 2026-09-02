from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    authority_registry: str = "authority/current/registry.json"
    authority_trusted_key_id: str | None = None
    authority_trusted_public_key: str | None = None
    live_execution: bool = False
    port: int = 8000

    model_config = SettingsConfigDict(
        env_prefix="GLOBAL_",
        case_sensitive=False,
        extra="ignore",
    )
