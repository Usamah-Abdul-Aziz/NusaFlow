"""
Centralized app configuration.

Replaces the previous pattern of calling os.getenv()/load_dotenv() directly
inside database.py, inventory_analysis.py, and main.py (including the manual
"strip quotes, try two candidate paths" dance that used to live in
main.py's _get_admin_api_key()). One Settings object, loaded once, used
everywhere — easier to see everything the app depends on in one place, and
easier to debug when a value isn't loading the way you expect.

Note on precedence: because the shared `.env` lives at the repo root
(one level above backend/) rather than inside backend/, both locations are
checked — backend/.env (if you ever add one) takes precedence over the
root .env for the same key.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./nusaflow.db"

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # Comma-separated list, e.g. "http://localhost:3000,https://nusaflow.vercel.app"
    CORS_ORIGINS: str = "*"

    # Cache TTL (seconds) for the in-memory average-daily-demand cache.
    CACHE_TTL: int = 300

    # Required to call /api/v1/admin/* endpoints. None disables them.
    ADMIN_API_KEY: str | None = None

    # Signs/verifies JWTs (see app/auth.py). The default below is fine for
    # local dev but MUST be overridden in any real deployment — main.py's
    # startup check refuses to start with the default when APP_ENV is not
    # "development", specifically so this can't be silently forgotten.
    SECRET_KEY: str = "dev-only-insecure-secret-change-me"

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
