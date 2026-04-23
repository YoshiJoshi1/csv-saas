from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


DEFAULT_DATABASE_URL = "sqlite:///app.sqlite3"


def _sanitize_database_url(value: str) -> str:
    cleaned = value.strip()
    if (cleaned.startswith("'") and cleaned.endswith("'")) or (
        cleaned.startswith('"') and cleaned.endswith('"')
    ):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def get_database_url() -> str:
    raw = (
        os.getenv("DATABASE_URL_INTERNAL")
        or os.getenv("APP_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )
    raw = _sanitize_database_url(raw)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw


@lru_cache(maxsize=8)
def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_database_url()
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


def execute(query: str, params: dict[str, Any] | None = None, database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(query), params or {})


def fetchone(
    query: str,
    params: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    engine = get_engine(database_url)
    with engine.begin() as connection:
        result = connection.execute(text(query), params or {})
        row = result.mappings().first()
        return dict(row) if row else None


def fetchall(
    query: str,
    params: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    engine = get_engine(database_url)
    with engine.begin() as connection:
        result = connection.execute(text(query), params or {})
        return [dict(row) for row in result.mappings().all()]


def check_database_connection(database_url: str | None = None) -> bool:
    engine = get_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
