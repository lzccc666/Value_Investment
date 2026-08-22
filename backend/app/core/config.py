from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "value_investment.db"
DEFAULT_BACKUP_DIRECTORY = PROJECT_ROOT / "data" / "backups"
DEFAULT_PROVIDER_CACHE_DIRECTORY = PROJECT_ROOT / "data" / "provider_cache"


class Settings(BaseSettings):
    app_name: str = "Value Investment API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api"
    database_url: str = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    backup_directory: Path = DEFAULT_BACKUP_DIRECTORY
    provider_cache_directory: Path = DEFAULT_PROVIDER_CACHE_DIRECTORY
    provider_timeout_seconds: float = 20.0
    sec_user_agent: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SEC_USER_AGENT", "VALUE_INVESTMENT_SEC_USER_AGENT"),
    )
    sec_max_requests_per_second: float = Field(default=8.0, ge=0.1, le=10.0)
    sec_cache_ttl_seconds: int = Field(default=21600, ge=0)
    hkex_cache_ttl_seconds: int = Field(default=21600, ge=0)
    ecb_cache_ttl_seconds: int = Field(default=21600, ge=0)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    model_provider: str = Field(
        default="openai_compatible",
        validation_alias=AliasChoices("MODEL_PROVIDER", "VALUE_INVESTMENT_MODEL_PROVIDER"),
    )
    model_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "MODEL_BASE_URL",
            "VALUE_INVESTMENT_MODEL_BASE_URL",
            "DEEPSEEK_BASE_URL",
        ),
    )
    model_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "MODEL_API_KEY",
            "VALUE_INVESTMENT_MODEL_API_KEY",
            "DEEPSEEK_API_KEY",
        ),
    )
    model_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "MODEL_NAME",
            "VALUE_INVESTMENT_MODEL_NAME",
            "DEEPSEEK_MODEL",
            "DEEPSEEK_MODEL_NAME",
        ),
    )
    model_wire_api: str = Field(
        default="chat_completions",
        validation_alias=AliasChoices("MODEL_WIRE_API", "VALUE_INVESTMENT_MODEL_WIRE_API"),
    )
    model_reasoning_effort: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "MODEL_REASONING_EFFORT",
            "VALUE_INVESTMENT_MODEL_REASONING_EFFORT",
        ),
    )
    model_disable_response_storage: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MODEL_DISABLE_RESPONSE_STORAGE",
            "VALUE_INVESTMENT_MODEL_DISABLE_RESPONSE_STORAGE",
        ),
    )
    model_timeout_seconds: float = Field(
        default=180,
        validation_alias=AliasChoices(
            "MODEL_TIMEOUT_SECONDS",
            "VALUE_INVESTMENT_MODEL_TIMEOUT_SECONDS",
        ),
    )

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_prefix="VALUE_INVESTMENT_",
        extra="ignore",
    )


settings = Settings()
