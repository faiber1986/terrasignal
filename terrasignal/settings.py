"""Project-wide settings (12-factor; env vars override defaults).

Local demo defaults point at the docker-compose Postgres on :5433. Governed
thresholds load from versioned YAML — they are policy, not env config.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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

    # CORS. The local Next.js dev server is always allowed via the regex below
    # (it hops ports when one is busy). Deployed frontends are opt-in: set
    # TERRASIGNAL_CORS_ALLOWED_ORIGINS to a comma-separated exact allowlist, e.g.
    # "https://terrasignal.vercel.app,https://terrasignal-git-main-acme.vercel.app".
    # Vercel mints a new hostname per preview deploy; to cover them set
    # TERRASIGNAL_CORS_ALLOW_ORIGIN_REGEX rather than widening the allowlist to "*"
    # (a wildcard is rejected by browsers when credentials are enabled).
    cors_allowed_origins: str = ""
    cors_allow_origin_regex: str = r"http://(localhost|127\.0\.0\.1):\d+"

    def cors_origin_list(self) -> list[str]:
        """Exact-match CORS origins, parsed from the comma-separated env var.

        Each entry is reduced to scheme://host[:port]. A browser's Origin header
        never carries a path, so a pasted page URL ("https://app.vercel.app/login")
        would otherwise never match — and the failure is invisible, because a
        rejected preflight looks exactly like a backend that is down.
        """
        origins = []
        for raw in self.cors_allowed_origins.split(","):
            entry = raw.strip()
            if not entry:
                continue
            parts = urlsplit(entry)
            if parts.netloc:
                origins.append(f"{parts.scheme}://{parts.netloc}")
            else:
                origins.append(entry.rstrip("/"))
        return origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def governed_thresholds() -> dict[str, Any]:
    settings = get_settings()
    with settings.governed_config_path.open(encoding="utf-8") as f:
        loaded: dict[str, Any] = yaml.safe_load(f)
    return loaded
