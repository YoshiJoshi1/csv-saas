from __future__ import annotations

import json
import os
from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import stripe
from sqlalchemy.exc import SQLAlchemyError

from db import execute, fetchone
from observability import get_logger


logger = get_logger("billing")


def _get_db_url(database_url: str | None = None) -> str | None:
    return database_url


def init_billing_db(database_url: str | None = None) -> None:
    db_url = _get_db_url(database_url)
    execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            has_paid INTEGER NOT NULL DEFAULT 0,
            free_files_used INTEGER NOT NULL DEFAULT 0,
            free_downloads_used INTEGER NOT NULL DEFAULT 0,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            subscription_status TEXT,
            current_period_end INTEGER,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        database_url=db_url,
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS processed_webhook_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        database_url=db_url,
    )
    for migration_sql in (
        "ALTER TABLE users ADD COLUMN user_id TEXT",
        "ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT",
        "ALTER TABLE users ADD COLUMN subscription_status TEXT",
        "ALTER TABLE users ADD COLUMN current_period_end INTEGER",
        "UPDATE users SET user_id = email WHERE user_id IS NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)",
    ):
        try:
            execute(migration_sql, database_url=db_url)
        except SQLAlchemyError:
            pass


def _ensure_user(user_id: str, email: str, database_url: str | None = None) -> None:
    execute(
        """
        INSERT INTO users (user_id, email)
        VALUES (:user_id, :email)
        ON CONFLICT (email) DO UPDATE
            SET user_id = COALESCE(users.user_id, EXCLUDED.user_id),
                updated_at = CURRENT_TIMESTAMP
        """,
        {"user_id": user_id, "email": email},
        database_url=_get_db_url(database_url),
    )


def get_user_status(user_id: str, email: str, database_url: str | None = None) -> Dict[str, Any]:
    _ensure_user(user_id, email, database_url=database_url)
    row = fetchone(
        """
        SELECT has_paid, free_files_used, free_downloads_used, subscription_status
        FROM users
        WHERE user_id = :user_id
        """,
        {"user_id": user_id},
        database_url=_get_db_url(database_url),
    )
    if not row:
        return {
            "has_paid": False,
            "free_files_used": 0,
            "free_downloads_used": 0,
            "subscription_status": None,
        }
    return {
        "has_paid": bool(row["has_paid"]),
        "free_files_used": int(row["free_files_used"]),
        "free_downloads_used": int(row["free_downloads_used"]),
        "subscription_status": row["subscription_status"],
    }


def record_free_file_use(user_id: str, email: str, database_url: str | None = None) -> None:
    _ensure_user(user_id, email, database_url=database_url)
    execute(
        """
        UPDATE users
        SET free_files_used = free_files_used + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
        """,
        {"user_id": user_id},
        database_url=_get_db_url(database_url),
    )


def record_free_download_use(user_id: str, email: str, database_url: str | None = None) -> None:
    _ensure_user(user_id, email, database_url=database_url)
    execute(
        """
        UPDATE users
        SET free_downloads_used = free_downloads_used + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
        """,
        {"user_id": user_id},
        database_url=_get_db_url(database_url),
    )


def _grants_access(subscription_status: str | None) -> bool:
    return subscription_status in {"active", "trialing"}


def mark_user_paid(
    user_id: str,
    email: str,
    stripe_customer_id: str | None = None,
    database_url: str | None = None,
) -> None:
    _ensure_user(user_id, email, database_url=database_url)
    execute(
        """
        UPDATE users
        SET has_paid = 1,
            email = :email,
            stripe_customer_id = COALESCE(:stripe_customer_id, stripe_customer_id),
            subscription_status = 'active',
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
        """,
        {"stripe_customer_id": stripe_customer_id, "user_id": user_id, "email": email},
        database_url=_get_db_url(database_url),
    )


def mark_user_access_revoked(user_id: str, database_url: str | None = None) -> None:
    execute(
        """
        UPDATE users
        SET has_paid = 0,
            subscription_status = 'canceled',
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
        """,
        {"user_id": user_id},
        database_url=_get_db_url(database_url),
    )


def _find_user_by_customer_id(customer_id: str, database_url: str | None = None) -> dict[str, str] | None:
    row = fetchone(
        "SELECT user_id, email FROM users WHERE stripe_customer_id = :customer_id",
        {"customer_id": customer_id},
        database_url=_get_db_url(database_url),
    )
    if not row:
        return None
    return {"user_id": str(row["user_id"]), "email": str(row["email"])}


def _update_subscription_status(
    *,
    user_id: str,
    email: str,
    subscription_id: str | None,
    status: str | None,
    current_period_end: int | None,
    stripe_customer_id: str | None = None,
    database_url: str | None = None,
) -> None:
    _ensure_user(user_id, email, database_url=database_url)
    has_paid = 1 if _grants_access(status) else 0
    execute(
        """
        UPDATE users
        SET has_paid = :has_paid,
            email = :email,
            stripe_customer_id = COALESCE(:stripe_customer_id, stripe_customer_id),
            stripe_subscription_id = COALESCE(:subscription_id, stripe_subscription_id),
            subscription_status = :status,
            current_period_end = COALESCE(:current_period_end, current_period_end),
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
        """,
        {
            "has_paid": has_paid,
            "email": email,
            "stripe_customer_id": stripe_customer_id,
            "subscription_id": subscription_id,
            "status": status,
            "current_period_end": current_period_end,
            "user_id": user_id,
        },
        database_url=_get_db_url(database_url),
    )


def _get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _append_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params[key] = value
    new_query = urlencode(params)
    return urlunparse(parsed._replace(query=new_query))


def create_checkout_session_url_for_user(user_id: str, email: str) -> str:
    stripe.api_key = _get_env("STRIPE_SECRET_KEY")
    price_id = _get_env("STRIPE_PRICE_ID")
    success_url = _append_query_param(_get_env("STRIPE_SUCCESS_URL"), "session_id", "{CHECKOUT_SESSION_ID}")
    cancel_url = _get_env("STRIPE_CANCEL_URL")

    session = stripe.checkout.Session.create(
        mode="payment",
        client_reference_id=user_id,
        customer_email=email,
        metadata={"user_id": user_id, "email": email},
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


def verify_checkout_session(session_id: str, expected_user_id: str) -> bool:
    stripe.api_key = _get_env("STRIPE_SECRET_KEY")
    session = stripe.checkout.Session.retrieve(session_id)
    paid = session.get("payment_status") == "paid"
    metadata = session.get("metadata", {}) or {}
    session_user_id = session.get("client_reference_id") or metadata.get("user_id")
    email = metadata.get("email") or session.get("customer_email")
    if paid and session_user_id == expected_user_id and isinstance(email, str):
        mark_user_paid(
            expected_user_id,
            email=email.lower(),
            stripe_customer_id=session.get("customer"),
        )
        return True
    return False


def construct_webhook_event(payload: bytes, signature_header: str) -> Dict[str, Any]:
    stripe.api_key = _get_env("STRIPE_SECRET_KEY")
    webhook_secret = _get_env("STRIPE_WEBHOOK_SECRET")

    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=signature_header,
        secret=webhook_secret,
    )
    to_dict = getattr(event, "to_dict_recursive", None)
    if callable(to_dict):
        return to_dict()
    return json.loads(str(event))


def _event_already_processed(event_id: str, database_url: str | None = None) -> bool:
    row = fetchone(
        "SELECT event_id FROM processed_webhook_events WHERE event_id = :event_id",
        {"event_id": event_id},
        database_url=_get_db_url(database_url),
    )
    return row is not None


def _mark_event_processed(event_id: str, event_type: str, database_url: str | None = None) -> None:
    execute(
        """
        INSERT INTO processed_webhook_events (event_id, event_type)
        VALUES (:event_id, :event_type)
        ON CONFLICT (event_id) DO NOTHING
        """,
        {"event_id": event_id, "event_type": event_type},
        database_url=_get_db_url(database_url),
    )


def _checkout_email(session_obj: Dict[str, Any]) -> str | None:
    metadata = session_obj.get("metadata", {}) or {}
    reference_email = metadata.get("email")
    customer_email = session_obj.get("customer_email")
    selected_email = reference_email or customer_email
    if isinstance(selected_email, str) and selected_email.strip():
        return selected_email.strip().lower()
    return None


def _checkout_user_id(session_obj: Dict[str, Any]) -> str | None:
    metadata = session_obj.get("metadata", {}) or {}
    selected_user_id = metadata.get("user_id") or session_obj.get("client_reference_id")
    if isinstance(selected_user_id, str) and selected_user_id.strip():
        return selected_user_id.strip()
    return None


def process_webhook_event(event: Dict[str, Any], database_url: str | None = None) -> Dict[str, Any]:
    """Process Stripe webhook events in an idempotent way."""
    event_id = str(event.get("id", ""))
    event_type = str(event.get("type", ""))
    if not event_id:
        return {"ok": False, "reason": "missing_event_id"}

    init_billing_db(database_url=database_url)
    if _event_already_processed(event_id, database_url=database_url):
        return {"ok": True, "status": "already_processed"}

    data_object = event.get("data", {}).get("object", {})
    user_identity: dict[str, str] | None = None

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        user_email = _checkout_email(data_object)
        user_id = _checkout_user_id(data_object)
        if user_email and user_id:
            mark_user_paid(
                user_id,
                user_email,
                stripe_customer_id=data_object.get("customer"),
                database_url=database_url,
            )
            _update_subscription_status(
                user_id=user_id,
                email=user_email,
                subscription_id=data_object.get("subscription"),
                status="active",
                current_period_end=None,
                stripe_customer_id=data_object.get("customer"),
                database_url=database_url,
            )
            user_identity = {"user_id": user_id, "email": user_email}
    elif event_type == "invoice.paid":
        customer_id = data_object.get("customer")
        if customer_id:
            user_identity = _find_user_by_customer_id(customer_id, database_url=database_url)
            if user_identity:
                mark_user_paid(
                    user_identity["user_id"],
                    user_identity["email"],
                    stripe_customer_id=customer_id,
                    database_url=database_url,
                )
    elif event_type in {"customer.subscription.updated", "customer.subscription.created"}:
        customer_id = data_object.get("customer")
        subscription_id = data_object.get("id")
        subscription_status = data_object.get("status")
        current_period_end = data_object.get("current_period_end")
        if customer_id:
            user_identity = _find_user_by_customer_id(customer_id, database_url=database_url)
            if user_identity:
                _update_subscription_status(
                    user_id=user_identity["user_id"],
                    email=user_identity["email"],
                    subscription_id=subscription_id,
                    status=subscription_status,
                    current_period_end=current_period_end,
                    stripe_customer_id=customer_id,
                    database_url=database_url,
                )
    elif event_type in {"customer.subscription.deleted", "invoice.payment_failed"}:
        customer_id = data_object.get("customer")
        if customer_id:
            user_identity = _find_user_by_customer_id(customer_id, database_url=database_url)
            if user_identity:
                mark_user_access_revoked(user_identity["user_id"], database_url=database_url)
    elif event_type == "checkout.session.expired":
        # No entitlement change needed.
        pass

    _mark_event_processed(event_id, event_type, database_url=database_url)
    if user_identity:
        logger.info(
            "processed_webhook_event",
            extra={
                "event_id": event_id,
                "event_type": event_type,
                "user_id": user_identity["user_id"],
            },
        )
    return {"ok": True, "status": "processed", "event_type": event_type}
