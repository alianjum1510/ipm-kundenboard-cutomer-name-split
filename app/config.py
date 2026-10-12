from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger("kundenname_split")


def _opt_int(name: str) -> int | None:
    raw = os.getenv(name)
    return int(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    max_name_length: int = int(os.getenv("MAX_NAME_LENGTH", "100"))
    teil2_max_length: int | None = _opt_int("TEIL2_MAX_LENGTH")
    api_version: str = os.getenv("MONDAY_API_VERSION", "2025-04")
    api_url: str = "https://api.monday.com/v2"


settings = Settings()

# key -> accepted names
REQUIRED_KEYS = {
    "MONDAY_API_TOKEN": ("MONDAY_API_TOKEN", "MONDAY_API_KEY"),
    "MONDAY_SIGNING_SECRET": ("MONDAY_SIGNING_SECRET",),
    "SOURCE_COLUMN_ID": ("SOURCE_COLUMN_ID",),
    "TARGET_COLUMN_ID": ("TARGET_COLUMN_ID",),
}


async def assert_configured() -> None:
    """Logs required keys that are missing. Logs rather than crashes, so /health still answers."""
    missing = [key for key, names in REQUIRED_KEYS.items() if not await get_secret(*names)]
    if missing:
        log.error("Missing required config: %s", ", ".join(missing))
    else:
        log.info("Config OK: %s set", ", ".join(REQUIRED_KEYS))

_cache: dict[str, str] = {}


async def get_secret(*keys: str) -> str:
    """
    Returns the first of `keys` that has a value, or "".

    A plain env var wins (local, Docker, tests). On monday-code, Secrets and
    Environment variables set in the Developer Center are not in os.environ; they
    are served by a local monday-code service, read through its SDK. Values are
    cached for the life of the process, so a changed secret needs a redeploy.
    """
    for key in keys:
        if os.getenv(key):
            return os.environ[key]
    for key in keys:
        if key not in _cache:
            value = await _from_monday_code(key)
            if not value:
                continue
            _cache[key] = value
        return _cache[key]
    return ""


async def _from_monday_code(key: str) -> str | None:
    try:
        import monday_code
        from monday_code.exceptions import NotFoundException
    except ImportError:
        return None

    try:
        async with monday_code.ApiClient(monday_code.Configuration()) as client:
            try:
                return await monday_code.SecretsApi(client).get_secret(key)
            except NotFoundException:
                pass
            try:
                value = await monday_code.EnvironmentVariablesApi(client).get_environment_variable(key)
            except NotFoundException:
                return None
            return None if value is None else str(value)
    except Exception as exc:  # noqa: BLE001 - not on monday-code, or the service is down
        log.warning("Could not read %s from monday-code: %s", key, exc)
        return None
