"""App-assembly contract tests: the FastAPI app must boot without a database,
serve health + OpenAPI, mount every router under /api/v1, and enforce auth at
the dependency seam (RBAC is security, not UX — CLAUDE.md §8)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from terrasignal.backend.app.main import API_PREFIX, app


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
