"""Project-wide settings (12-factor; env vars override defaults).

Local demo defaults point at the docker-compose Postgres on :5433. Governed
thresholds load from versioned YAML — they are policy, not env config.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TERRASIGNAL_ROOT = PROJECT_ROOT / "terrasignal"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TERRASIGNAL_", env_file=".env", extra="ignore")

    database_url_sync: str = (
        "postgresql+psycopg://terrasignal:terrasignal_local_dev@localhost:5433/terrasignal"
    )
    database_url_async: str = (
        "postgresql+asyncpg://terrasignal:terrasignal_local_dev@localhost:5433/terrasignal"
    )
    data_dir: Path = TERRASIGNAL_ROOT / "data"
    artifacts_dir: Path = TERRASIGNAL_ROOT / "artifacts"
    governed_config_path: Path = TERRASIGNAL_ROOT / "config" / "governed" / "thresholds.yaml"
    jwt_secret: str = "local-demo-secret-do-not-use-in-prod"
    rationale_backend: str = "template"  # template | bedrock


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def governed_thresholds() -> dict[str, Any]:
    settings = get_settings()
    with settings.governed_config_path.open(encoding="utf-8") as f:
        loaded: dict[str, Any] = yaml.safe_load(f)
    return loaded
