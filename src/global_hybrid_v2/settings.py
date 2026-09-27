from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MediaCapabilityDebt(RuntimeError):
    pass


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
    vehicle_configuration_snapshot_path: str | None = None
    vehicle_configuration_provider_mode: str = "file"
    vehicle_configuration_http_base_url: str | None = None
    vehicle_configuration_http_read_secret: str | None = None
    vehicle_reconciliation_shared_secret: SecretStr | None = None
    google_service_account_json: SecretStr | None = None
    vehicle_control_http_base_url: str | None = None
    vehicle_control_http_write_secret: SecretStr | None = None
    media_enabled: bool = False
    media_registry_base_url: str | None = None
    media_registry_read_secret: SecretStr | None = None
    media_registry_write_secret: SecretStr | None = None
    media_r2_binding: str | None = None
    media_activity_signing_key_ref: str | None = None
    ingress_turn_signing_key_ref: str | None = None
    expected_control_plane_schema_revision: str | None = None

    def require_media_deployment_bindings(self) -> None:
        required = (
            self.media_registry_base_url,
            self.media_registry_read_secret,
            self.media_registry_write_secret,
            self.media_r2_binding,
            self.media_activity_signing_key_ref,
            self.ingress_turn_signing_key_ref,
            self.expected_control_plane_schema_revision,
        )
        if any(not value for value in required):
            raise MediaCapabilityDebt("MEDIA_DEPLOYMENT_BINDING_INCOMPLETE")
        if self.media_r2_binding != "MEDIA_BUCKET":
            raise MediaCapabilityDebt("MEDIA_R2_BINDING_MISMATCH")
        if self.expected_control_plane_schema_revision != "0002_media_asset":
            raise MediaCapabilityDebt("MEDIA_SCHEMA_REVISION_MISMATCH")
        if not self.media_registry_base_url.startswith("https://"):
            raise MediaCapabilityDebt("MEDIA_REGISTRY_URL_INVALID")

    model_config = SettingsConfigDict(
        env_prefix="GLOBAL_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )
