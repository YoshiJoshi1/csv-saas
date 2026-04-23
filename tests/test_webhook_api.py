from __future__ import annotations

import os

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

os.environ.setdefault("DATABASE_URL", "sqlite:///test_webhook.sqlite3")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_placeholder")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")

import webhook_api


def test_webhook_missing_signature_returns_400() -> None:
    client = TestClient(webhook_api.app)
    response = client.post("/stripe/webhook", content=b"{}")
    assert response.status_code == 400


def test_webhook_invalid_signature_returns_400(monkeypatch) -> None:
    client = TestClient(webhook_api.app)

    def fake_construct(_payload: bytes, _signature: str) -> dict[str, str]:
        raise ValueError("invalid payload")

    monkeypatch.setattr(webhook_api, "construct_webhook_event", fake_construct)
    response = client.post(
        "/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "bad"},
    )
    assert response.status_code == 400


def test_webhook_success(monkeypatch) -> None:
    client = TestClient(webhook_api.app)

    def fake_construct(_payload: bytes, _signature: str) -> dict[str, str]:
        return {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {}}}

    def fake_process(_event: dict[str, str]) -> dict[str, str]:
        return {"ok": True}

    monkeypatch.setattr(webhook_api, "construct_webhook_event", fake_construct)
    monkeypatch.setattr(webhook_api, "process_webhook_event", fake_process)
    response = client.post(
        "/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "ok"},
    )
    assert response.status_code == 200


def test_webhook_transient_error_returns_503(monkeypatch) -> None:
    client = TestClient(webhook_api.app)

    def fake_construct(_payload: bytes, _signature: str) -> dict[str, str]:
        return {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {}}}

    def fake_process(_event: dict[str, str]) -> dict[str, str]:
        raise SQLAlchemyError("db unavailable")

    monkeypatch.setattr(webhook_api, "construct_webhook_event", fake_construct)
    monkeypatch.setattr(webhook_api, "process_webhook_event", fake_process)
    response = client.post(
        "/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "ok"},
    )
    assert response.status_code == 503
