"""initial schema

Revision ID: 20260411_000001
Revises:
Create Date: 2026-04-11 18:31:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260411_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("has_paid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("free_files_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("free_downloads_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),
        sa.Column("stripe_subscription_id", sa.Text(), nullable=True),
        sa.Column("subscription_status", sa.Text(), nullable=True),
        sa.Column("current_period_end", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "processed_webhook_events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade() -> None:
    op.drop_table("processed_webhook_events")
    op.drop_table("users")
