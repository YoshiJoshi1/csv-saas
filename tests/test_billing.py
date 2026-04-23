from __future__ import annotations

from pathlib import Path

from billing import get_user_status, init_billing_db, process_webhook_event
from db import fetchone


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'billing_test.sqlite3'}"


def test_checkout_event_marks_user_paid(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    init_billing_db(database_url=db_url)

    event = {
        "id": "evt_checkout_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "user_1",
                "customer": "cus_123",
                "subscription": "sub_123",
                "customer_email": "test@example.com",
                "metadata": {"user_id": "user_1", "email": "test@example.com"},
            }
        },
    }

    result = process_webhook_event(event, database_url=db_url)
    assert result["ok"] is True

    status = get_user_status("user_1", "test@example.com", database_url=db_url)
    assert status["has_paid"] is True
    assert status["subscription_status"] == "active"


def test_duplicate_webhook_is_idempotent(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    init_billing_db(database_url=db_url)

    event = {
        "id": "evt_duplicate_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "user_dup",
                "customer": "cus_dup",
                "customer_email": "dup@example.com",
                "metadata": {"user_id": "user_dup", "email": "dup@example.com"},
            }
        },
    }

    first = process_webhook_event(event, database_url=db_url)
    second = process_webhook_event(event, database_url=db_url)

    assert first["ok"] is True
    assert second["status"] == "already_processed"

    row = fetchone(
        "SELECT COUNT(*) AS total FROM processed_webhook_events WHERE event_id = :event_id",
        {"event_id": "evt_duplicate_1"},
        database_url=db_url,
    )
    count = int(row["total"]) if row else 0
    assert count == 1


def test_subscription_deleted_revokes_access(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    init_billing_db(database_url=db_url)
    process_webhook_event(
        {
            "id": "evt_seed_paid",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "user_revoke",
                    "customer": "cus_revoke",
                    "customer_email": "rev@example.com",
                    "metadata": {"user_id": "user_revoke", "email": "rev@example.com"},
                }
            },
        },
        database_url=db_url,
    )

    process_webhook_event(
        {
            "id": "evt_sub_deleted",
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_revoke"}},
        },
        database_url=db_url,
    )
    status = get_user_status("user_revoke", "rev@example.com", database_url=db_url)
    assert status["has_paid"] is False
