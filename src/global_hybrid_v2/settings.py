from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    authority_registry: str = "authority/current/registry.json"
    live_execution: bool = False
    port: int = 8000

    model_config = SettingsConfigDict(
        env_prefix="GLOBAL_",
        case_sensitive=False,
        extra="ignore",
    )
