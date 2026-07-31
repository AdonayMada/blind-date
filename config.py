"""
config.py
Centralized configuration loaded from environment variables.

Works with Render's environment variable injection and local .env files
(via python-dotenv, loaded only if present — safe for production).
"""

import logging
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()  # no-op in production if .env doesn't exist
except ImportError:
    pass

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def _get_env(name: str, required: bool = True, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    BOT_TOKEN: str
    MONGO_URI: str
    MONGO_DB_NAME: str
    ADMIN_IDS: tuple[int, ...]
    MIN_AGE: int
    MAX_AGE: int
    ENVIRONMENT: str


def load_settings() -> Settings:
    """Loads and validates all settings. Raises ConfigError on failure."""
    try:
        admin_ids_raw = _get_env("ADMIN_IDS", required=False, default="")
        admin_ids = tuple(
            int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()
        )

        return Settings(
            BOT_TOKEN=_get_env("BOT_TOKEN"),
            MONGO_URI=_get_env("MONGO_URI"),
            MONGO_DB_NAME=_get_env("MONGO_DB_NAME", required=False, default="blind_date_bot"),
            ADMIN_IDS=admin_ids,
            MIN_AGE=int(_get_env("MIN_AGE", required=False, default="18")),
            MAX_AGE=int(_get_env("MAX_AGE", required=False, default="99")),
            ENVIRONMENT=_get_env("ENVIRONMENT", required=False, default="production"),
        )
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc


try:
    settings = load_settings()
except ConfigError as e:
    logger.critical("Configuration error: %s", e)
    raise
