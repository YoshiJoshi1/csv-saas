from __future__ import annotations

import os
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from stripe import SignatureVerificationError
from sqlalchemy.exc import SQLAlchemyError

from billing import construct_webhook_event, init_billing_db, process_webhook_event
from db import check_database_connection
from observability import configure_logging, get_logger, init_sentry, required_env_vars


app = FastAPI(title="Stripe Webhook Service")
configure_logging("webhook-api")
init_sentry("webhook-api")
logger = get_logger("webhook_api")
startup_warnings: list[str] = []


def _database_env_present() -> bool:
    return bool(
        os.getenv("DATABASE_URL_INTERNAL", "").strip()
        or os.getenv("APP_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )


try:
    init_billing_db()
except Exception as error:
    startup_warnings.append("billing_db_init_failed")
    logger.warning("billing_db_init_failed", extra={"error": str(error)})

if not _database_env_present():
    startup_warnings.append("database_url_missing")
if required_env_vars(["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"]):
    startup_warnings.append("stripe_env_missing")


@app.get("/health")
def health() -> dict[str, str | bool]:
    stripe_ready = len(required_env_vars(["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"])) == 0
    db_ready = check_database_connection()
    status = "ok" if stripe_ready and db_ready else "degraded"
    return {
        "status": status,
        "database": db_ready,
        "stripe_configured": stripe_ready,
        "startup_warnings": ",".join(startup_warnings) if startup_warnings else "",
    }


@app.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, str]:
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    if required_env_vars(["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"]):
        raise HTTPException(status_code=503, detail="Webhook service not configured")
    if not check_database_connection():
        raise HTTPException(status_code=503, detail="Database unavailable")

    request_id = str(uuid.uuid4())
    max_body_kb = int(os.getenv("MAX_WEBHOOK_BODY_KB", "256"))
    max_body_size = max_body_kb * 1024
    content_length = int(request.headers.get("content-length", "0"))
    if content_length > max_body_size:
        logger.warning("webhook_payload_too_large", extra={"request_id": request_id})
        raise HTTPException(status_code=413, detail="Payload too large")

    payload = await request.body()
    if len(payload) > max_body_size:
        logger.warning("webhook_payload_too_large_runtime", extra={"request_id": request_id})
        raise HTTPException(status_code=413, detail="Payload too large")

    try:
        event = construct_webhook_event(payload, stripe_signature)
        process_webhook_event(event)
    except SignatureVerificationError as error:
        logger.warning("invalid_webhook_signature", extra={"request_id": request_id})
        raise HTTPException(status_code=400, detail="Invalid signature") from error
    except ValueError as error:
        logger.warning("invalid_webhook_payload", extra={"request_id": request_id})
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from error
    except SQLAlchemyError as error:
        logger.error("database_error_processing_webhook", extra={"request_id": request_id})
        raise HTTPException(status_code=503, detail="Temporary processing failure") from error
    except Exception as error:
        logger.exception("unexpected_webhook_failure", extra={"request_id": request_id})
        raise HTTPException(status_code=500, detail="Internal processing error") from error

    return {"status": "received"}
