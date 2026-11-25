from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="BizPresence AI")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # Google Gemini LLM
    gemini_api_key: str | None = Field(default=None)

    # Google Business Profile & OAuth
    google_business_account_id: str | None = Field(default=None)
    google_business_location_id: str | None = Field(default=None)
    google_client_id: str | None = Field(default=None)
    google_client_secret: str | None = Field(default=None)

    # Facebook Graph API
    facebook_page_token: str | None = Field(default=None)
    facebook_page_id: str | None = Field(default=None)

    # Instagram Graph API
    instagram_access_token: str | None = Field(default=None)
    instagram_business_id: str | None = Field(default=None)

    # Twitter / X API
    twitter_api_key: str | None = Field(default=None)
    twitter_api_secret: str | None = Field(default=None)
    twitter_access_token: str | None = Field(default=None)
    twitter_access_secret: str | None = Field(default=None)

    # Database
    database_url: str = Field(default="sqlite:///./bizpresence.db")

    @property
    def async_database_url(self) -> str:
        """Return an async-compatible SQLAlchemy database URL."""
        if self.database_url.startswith("sqlite+aiosqlite://"):
            return self.database_url
        if self.database_url.startswith("sqlite://"):
            return self.database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()


settings: Settings = get_settings()
