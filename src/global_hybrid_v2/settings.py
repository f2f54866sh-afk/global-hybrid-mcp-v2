from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    authority_registry: str = "authority/current/registry.json"
    authority_trusted_key_id: str | None = None
    authority_trusted_public_key: str | None = None
    research_provider: str = "disabled"
    research_model: str | None = None
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "GLOBAL_OPENAI_API_KEY"),
    )
    live_execution: bool = False
    port: int = 8000

    model_config = SettingsConfigDict(
        env_prefix="GLOBAL_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )
