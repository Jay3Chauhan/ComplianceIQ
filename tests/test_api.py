"""Smoke tests for the FastAPI app."""

from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_root_endpoint() -> None:
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "ComplianceIQ"
    assert "docs" in body


def test_health_endpoint_responds() -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["collection_name"]
    assert body["model"]
    assert body["status"] in {"healthy", "degraded"}


def test_query_validation_rejects_short_question() -> None:
    res = client.post("/api/query", json={"question": "hi"})
    assert res.status_code == 422
