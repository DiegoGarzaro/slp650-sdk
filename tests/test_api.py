"""Tests for slp650_sdk.api (no printer hardware required)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from slp650_sdk import api
from slp650_sdk.api import app
from slp650_sdk.protocol import tokenize

API_KEY = "test-key"


@pytest.fixture
def captured_streams(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """Divert native sends into a list instead of a printer device."""
    streams: list[bytes] = []

    def fake_send(data: bytes, config: object, copies: int = 1) -> None:
        streams.append(data)

    monkeypatch.setattr(api, "send_native_stream", fake_send)
    return streams


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
        "pdf_support",
        "ppd_present",
        "filter_present",
        "cupsfilter_present",
    }


def test_health_ok_needs_only_the_device(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    device = Path(str(tmp_path)) / "lp0"
    device.write_bytes(b"")
    monkeypatch.setenv("SLP650_DEVICE", str(device))
    body = client.get("/health", headers={"X-API-Key": API_KEY}).json()
    assert body["ok"] is True
    assert body["device_present"] is True


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


def test_print_text_end_to_end_native(
    client: TestClient, captured_streams: list[bytes]
) -> None:
    response = client.post(
        "/print/text",
        headers={"X-API-Key": API_KEY},
        json={"text": "Hello SLP650", "media": "MediaBadge"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "native"
    assert body["native_bytes_per_copy"] == len(captured_streams[0])
    # The stream must be a valid label: header commands and a FormFeed.
    tokens = tokenize(captured_streams[0])
    assert tokens[0].name == "Margin"
    assert tokens[-1].name == "FormFeed"


def test_print_image_native_fits_any_size(
    client: TestClient, captured_streams: list[bytes]
) -> None:
    upload = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(upload, format="PNG")
    response = client.post(
        "/print/image",
        headers={"X-API-Key": API_KEY},
        files={"file": ("photo.png", upload.getvalue())},
        data={"media": "AddressSmall"},
    )
    assert response.status_code == 200
    assert response.json()["engine"] == "native"
    assert len(captured_streams) == 1


def test_print_image_falls_back_to_cups_for_non_images(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def fake_print_file(path: Path, config: object, copies: int = 1) -> int:
        calls.append(path)
        return 42

    monkeypatch.setattr(api, "print_file", fake_print_file)
    response = client.post(
        "/print/image",
        headers={"X-API-Key": API_KEY},
        files={"file": ("doc.pdf", b"%PDF-1.4 not really an image")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "cups"
    assert body["native_bytes_per_copy"] == 42
    assert len(calls) == 1
    assert calls[0].suffix == ".pdf"


def test_print_image_rejects_unknown_media(
    client: TestClient, captured_streams: list[bytes]
) -> None:
    upload = io.BytesIO()
    Image.new("1", (10, 10), 255).save(upload, format="PNG")
    response = client.post(
        "/print/image",
        headers={"X-API-Key": API_KEY},
        files={"file": ("a.png", upload.getvalue())},
        data={"media": "Bogus"},
    )
    assert response.status_code == 422
    assert captured_streams == []


def test_print_raw_rejects_empty_upload(client: TestClient) -> None:
    response = client.post(
        "/print/raw",
        headers={"X-API-Key": API_KEY},
        files={"file": ("label.slp", b"")},
    )
    assert response.status_code == 422
