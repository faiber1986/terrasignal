"""App-assembly contract tests: the FastAPI app must boot without a database,
serve health + OpenAPI, mount every router under /api/v1, and enforce auth at
the dependency seam (RBAC is security, not UX — CLAUDE.md §8).

CORS is covered here too: a deployed frontend reaches the API only if its origin
is configured, and an unconfigured origin must stay rejected. Both directions are
asserted — an allowlist nobody tests is the same as no allowlist."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from terrasignal.backend.app.main import API_PREFIX, app
from terrasignal.settings import get_settings


def test_health_boots_without_db() -> None:
    # The lifespan model load fails closed (no DB) but the app still boots.
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_request_id_echoed() -> None:
    with TestClient(app) as client:
        r = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert r.headers["X-Request-ID"] == "trace-123"


def test_openapi_contract_is_serveable() -> None:
    with TestClient(app) as client:
        spec = client.get(f"{API_PREFIX}/openapi.json").json()
    paths = spec["paths"]
    # Every router is mounted under the versioned prefix.
    assert f"{API_PREFIX}/auth/login" in paths
    assert f"{API_PREFIX}/risk/queue" in paths
    assert f"{API_PREFIX}/risk/score" in paths
    assert f"{API_PREFIX}/forecasts/rent" in paths
    assert f"{API_PREFIX}/feedback" in paths
    assert f"{API_PREFIX}/models/active" in paths
    assert f"{API_PREFIX}/portfolio/summary" in paths
    assert f"{API_PREFIX}/governance/kill-switch" in paths
    # The kill switch read+write share a path; the write is admin-gated.
    assert {"get", "post"} <= set(paths[f"{API_PREFIX}/governance/kill-switch"])


def test_login_issues_token_then_protected_route_accepts_it() -> None:
    with TestClient(app) as client:
        # Protected route rejects anonymous callers at the auth dependency,
        # before any DB access.
        assert client.get(f"{API_PREFIX}/risk/queue").status_code == 401

        login = client.post(
            f"{API_PREFIX}/auth/login",
            json={"username": "ana.analyst", "password": "demo"},
        )
        assert login.status_code == 200
        body = login.json()
        assert body["role"] == "analyst" and body["token"]

        # Bad credentials are rejected.
        bad = client.post(
            f"{API_PREFIX}/auth/login",
            json={"username": "ana.analyst", "password": "wrong"},
        )
        assert bad.status_code == 401


# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #


@pytest.fixture
def rebuilt_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., FastAPI]]:
    """Rebuild the app with CORS env vars applied.

    Middleware is wired at import time from cached settings, so an env-driven
    allowlist can only be exercised by clearing the cache and reloading the
    module. The fixture restores both afterwards so later tests see the default.
    """
    import terrasignal.backend.app.main as main_mod

    def build(**env: str) -> FastAPI:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        return importlib.reload(main_mod).app

    yield build

    monkeypatch.undo()
    get_settings.cache_clear()
    importlib.reload(main_mod)


def _preflight(built: FastAPI, origin: str) -> str | None:
    """Return the allow-origin header a browser would receive, or None if blocked."""
    response = TestClient(built).options(
        f"{API_PREFIX}/auth/login",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    return response.headers.get("access-control-allow-origin")


def test_local_dev_origin_allowed_by_default() -> None:
    # The dev server hops ports when one is busy, so any localhost port matches.
    assert _preflight(app, "http://localhost:3001") == "http://localhost:3001"
    assert _preflight(app, "http://127.0.0.1:3000") == "http://127.0.0.1:3000"


def test_unconfigured_origin_rejected_by_default() -> None:
    # A deployed frontend is opt-in: nothing is allowed until it is configured.
    assert _preflight(app, "https://your-app.vercel.app") is None


def test_configured_deployment_origin_allowed(rebuilt_app: Callable[..., FastAPI]) -> None:
    built = rebuilt_app(
        TERRASIGNAL_CORS_ALLOWED_ORIGINS="https://terrasignal.vercel.app, https://staging.example.com/"
    )
    # Trailing slashes are stripped: an Origin header never carries one, so a
    # pasted "https://host/" would otherwise silently never match.
    assert _preflight(built, "https://terrasignal.vercel.app") == "https://terrasignal.vercel.app"
    assert _preflight(built, "https://staging.example.com") == "https://staging.example.com"
    # Configuring one deployment does not open the door to every other origin.
    assert _preflight(built, "https://evil.example.com") is None
    # ...and local development keeps working alongside it.
    assert _preflight(built, "http://localhost:3001") == "http://localhost:3001"


def test_origin_regex_covers_preview_deploys(rebuilt_app: Callable[..., FastAPI]) -> None:
    # Vercel mints a hostname per preview deploy; a regex covers them all.
    built = rebuilt_app(
        TERRASIGNAL_CORS_ALLOW_ORIGIN_REGEX=r"https://terrasignal-[a-z0-9-]+\.vercel\.app"
    )
    preview = "https://terrasignal-git-feat-x-acme.vercel.app"
    assert _preflight(built, preview) == preview
    assert _preflight(built, "https://other-project.vercel.app") is None
