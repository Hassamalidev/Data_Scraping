from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# scraper/src/mbd/config.py -> repo root is three levels up from this package.
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings, read from the environment and the repo-root `.env`."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgres://mbd:mbd@localhost:5432/mbd"
    database_url_direct: str | None = None

    scraper_user_agent: str = "CanadaHalalDirectoryBot/1.0"
    scraper_default_delay_seconds: float = 3.0
    nominatim_email: str = ""
    google_places_api_key: str = ""

    raw_data_dir: Path = REPO_ROOT / "data" / "raw"
    exports_dir: Path = REPO_ROOT / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
