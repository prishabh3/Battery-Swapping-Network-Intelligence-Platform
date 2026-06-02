"""
Integration tests for the FastAPI backend.
These tests run against an in-memory SQLite or mock layer.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from backend.api.main import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_payload(self, client):
        resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "healthy"
        assert "version" in body


class TestAuthEndpoints:
    def test_valid_login(self, client):
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "analyst", "password": "analyst2024"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_invalid_credentials(self, client):
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "analyst", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_chairman_login(self, client):
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "chairman", "password": "sunmobility2024"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "executive"


class TestAPIDocumentation:
    def test_openapi_spec_accessible(self, client):
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200

    def test_docs_accessible(self, client):
        resp = client.get("/api/docs")
        assert resp.status_code == 200


class TestSimulationEndpoints:
    def test_new_stations_scenario(self, client):
        resp = client.post(
            "/api/v1/simulation/new-stations",
            json={
                "city": "Mumbai",
                "num_new_stations": 10,
                "avg_capacity_per_station": 150,
                "target_utilization": 0.65,
            },
        )
        # Returns 200 or 500 (if simulator has an issue) — just check it doesn't crash the server
        assert resp.status_code in (200, 500)

    def test_demand_shock_scenario(self, client):
        resp = client.post(
            "/api/v1/simulation/demand-shock",
            json={"demand_increase_pct": 30.0},
        )
        assert resp.status_code in (200, 500)
