from __future__ import annotations

import logging
import os
from typing import Any


_configured = False


def configure_logging(service_name: str) -> None:
    global _configured
    if _configured:
        return
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=f"%(asctime)s %(levelname)s {service_name} %(name)s %(message)s",
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def init_sentry(service_name: str) -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=traces_sample_rate,
            environment=os.getenv("APP_ENV", "production"),
            release=os.getenv("APP_VERSION", "local"),
            server_name=service_name,
        )
    except Exception:
        logging.getLogger(name=service_name).warning("sentry_initialization_failed")


def required_env_vars(names: list[str]) -> list[str]:
    missing: list[str] = []
    for name in names:
        if not os.getenv(name, "").strip():
            missing.append(name)
    return missing


def log_kv(logger: logging.Logger, message: str, **kwargs: Any) -> None:
    if kwargs:
        extra = " ".join([f"{key}={value}" for key, value in kwargs.items()])
        logger.info("%s %s", message, extra)
    else:
        logger.info("%s", message)
