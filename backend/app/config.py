from functools import lru_cache
from pathlib import Path

from pydantic import (
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

BACKEND_DIRECTORY = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = Field(
        default="Trip Logic API",
        validation_alias="APP_NAME",
    )

    environment: str = Field(
        default="development",
        validation_alias="ENVIRONMENT",
    )

    firebase_credentials_path: Path = Field(
        validation_alias="FIREBASE_CREDENTIALS_PATH",
    )

    foursquare_api_key: SecretStr = Field(
        validation_alias="FOURSQUARE_API_KEY",
    )

    openrouteservice_api_key: SecretStr = Field(
        validation_alias="OPENROUTESERVICE_API_KEY",
    )

    openai_api_key: SecretStr = Field(
        validation_alias="OPENAI_API_KEY",
    )

    openai_model: str = Field(
        default="gpt-5-mini",
        validation_alias="OPENAI_MODEL",
    )

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIRECTORY / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("firebase_credentials_path")
    @classmethod
    def validate_firebase_credentials_path(
        cls,
        value: Path,
    ) -> Path:
        resolved_path = value.expanduser().resolve()

        if not resolved_path.is_file():
            raise ValueError(
                "Firebase credentials file was not found: " f"{resolved_path}"
            )

        if resolved_path.suffix.lower() != ".json":
            raise ValueError("Firebase credentials must be a JSON file.")

        return resolved_path

    @field_validator(
        "foursquare_api_key",
        "openrouteservice_api_key",
        "openai_api_key",
    )
    @classmethod
    def validate_api_key(
        cls,
        value: SecretStr,
        info: ValidationInfo,
    ) -> SecretStr:
        raw_value = value.get_secret_value().strip()

        if not raw_value:
            raise ValueError(f"{info.field_name} cannot be empty.")

        if raw_value.upper().startswith("PASTE_"):
            raise ValueError("Replace the placeholder value for " f"{info.field_name}.")

        return SecretStr(raw_value)

    @field_validator("openai_model")
    @classmethod
    def validate_openai_model(
        cls,
        value: str,
    ) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError("openai_model cannot be empty.")

        if normalized_value.upper().startswith("PASTE_"):
            raise ValueError("Replace the placeholder value for openai_model.")

        if any(character.isspace() for character in normalized_value):
            raise ValueError("openai_model cannot contain spaces.")

        return normalized_value


@lru_cache
def get_settings() -> Settings:
    return Settings()
