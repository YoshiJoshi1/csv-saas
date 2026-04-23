from __future__ import annotations

import argparse
import os
import sqlite3
import uuid
from pathlib import Path

from billing import init_billing_db
from db import execute
from observability import configure_logging, get_logger


configure_logging("migration")
logger = get_logger("migration")


def _stable_user_id(email: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"user:{email.lower()}"))


def _migrate_billing_users(
    legacy_billing_db: Path,
    *,
    database_url: str | None = None,
    dry_run: bool = False,
) -> int:
    if not legacy_billing_db.exists():
        return 0

    moved = 0
    with sqlite3.connect(str(legacy_billing_db)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM users").fetchall()
        except sqlite3.OperationalError:
            return 0
        for row in rows:
            email = str(row["email"]).lower()
            user_id = row["user_id"] if "user_id" in row.keys() and row["user_id"] else _stable_user_id(email)
            if dry_run:
                moved += 1
                continue
            execute(
                """
                INSERT INTO users (
                    user_id,
                    email,
                    has_paid,
                    free_files_used,
                    free_downloads_used,
                    stripe_customer_id,
                    stripe_subscription_id,
                    subscription_status,
                    current_period_end
                )
                VALUES (
                    :user_id,
                    :email,
                    :has_paid,
                    :free_files_used,
                    :free_downloads_used,
                    :stripe_customer_id,
                    :stripe_subscription_id,
                    :subscription_status,
                    :current_period_end
                )
                ON CONFLICT (user_id) DO UPDATE SET
                    email = EXCLUDED.email,
                    has_paid = EXCLUDED.has_paid,
                    free_files_used = EXCLUDED.free_files_used,
                    free_downloads_used = EXCLUDED.free_downloads_used,
                    stripe_customer_id = COALESCE(EXCLUDED.stripe_customer_id, users.stripe_customer_id),
                    stripe_subscription_id = COALESCE(EXCLUDED.stripe_subscription_id, users.stripe_subscription_id),
                    subscription_status = COALESCE(EXCLUDED.subscription_status, users.subscription_status),
                    current_period_end = COALESCE(EXCLUDED.current_period_end, users.current_period_end),
                    updated_at = CURRENT_TIMESTAMP
                """,
                {
                    "user_id": user_id,
                    "email": email,
                    "has_paid": row["has_paid"],
                    "free_files_used": row["free_files_used"],
                    "free_downloads_used": row["free_downloads_used"],
                    "stripe_customer_id": row["stripe_customer_id"],
                    "stripe_subscription_id": row["stripe_subscription_id"]
                    if "stripe_subscription_id" in row.keys()
                    else None,
                    "subscription_status": row["subscription_status"]
                    if "subscription_status" in row.keys()
                    else None,
                    "current_period_end": row["current_period_end"]
                    if "current_period_end" in row.keys()
                    else None,
                },
                database_url=database_url,
            )
            moved += 1
    return moved


def _migrate_webhook_events(
    legacy_billing_db: Path,
    *,
    database_url: str | None = None,
    dry_run: bool = False,
) -> int:
    if not legacy_billing_db.exists():
        return 0

    moved = 0
    with sqlite3.connect(str(legacy_billing_db)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT event_id, event_type FROM processed_webhook_events").fetchall()
        except sqlite3.OperationalError:
            return 0
        for row in rows:
            if dry_run:
                moved += 1
                continue
            execute(
                """
                INSERT INTO processed_webhook_events (event_id, event_type)
                VALUES (:event_id, :event_type)
                ON CONFLICT (event_id) DO NOTHING
                """,
                {"event_id": row["event_id"], "event_type": row["event_type"]},
                database_url=database_url,
            )
            moved += 1
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy SQLite billing data into DATABASE_URL.")
    parser.add_argument("--dry-run", action="store_true", help="Show row counts without writing.")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    legacy_billing_db = Path(os.getenv("LEGACY_BILLING_DB_PATH", "billing.sqlite3"))

    init_billing_db(database_url=database_url)

    moved_users = _migrate_billing_users(
        legacy_billing_db,
        database_url=database_url,
        dry_run=args.dry_run,
    )
    moved_events = _migrate_webhook_events(
        legacy_billing_db,
        database_url=database_url,
        dry_run=args.dry_run,
    )

    mode = "DRY RUN" if args.dry_run else "WRITE MODE"
    logger.info("migration_finished mode=%s users=%s events=%s", mode, moved_users, moved_events)
    print(f"Migration finished ({mode}).")
    print(f"Billing users migrated: {moved_users}")
    print(f"Webhook events migrated: {moved_events}")


if __name__ == "__main__":
    main()
