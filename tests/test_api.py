"""Tests for slp650_sdk.api (no printer hardware required)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from slp650_sdk.api import app

API_KEY = "test-key"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SLP650_API_KEY", API_KEY)
    return TestClient(app)


def test_requests_refused_without_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLP650_API_KEY", raising=False)
    response = TestClient(app).get("/health")
    assert response.status_code == 503


def test_wrong_key_is_unauthorized(client: TestClient) -> None:
    response = client.get("/health", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_missing_key_is_unauthorized(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 401


def test_health_reports_environment(client: TestClient) -> None:
    response = client.get("/health", headers={"X-API-Key": API_KEY})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "ok",
        "device",
        "device_present",
        "ppd_present",
        "filter_present",
        "cupsfilter_present",
    }


def test_print_text_rejects_unknown_media(client: TestClient) -> None:
    response = client.post(
        "/print/text",
        headers={"X-API-Key": API_KEY},
        json={"text": "hi", "media": "Bogus"},
    )
    assert response.status_code == 422
    assert "Unsupported media" in response.json()["detail"]


def test_print_text_rejects_invalid_rotation(client: TestClient) -> None:
    response = client.post(
        "/print/text",
        headers={"X-API-Key": API_KEY},
        json={"text": "hi", "rotate": 45},
    )
    assert response.status_code == 422


def test_print_raw_rejects_empty_upload(client: TestClient) -> None:
    response = client.post(
        "/print/raw",
        headers={"X-API-Key": API_KEY},
        files={"file": ("label.slp", b"")},
    )
    assert response.status_code == 422
