"""Send a Stripe-signed test event to the production webhook.

Simulates Stripe's exact signing scheme so we validate:
- TLS + routing reach the Railway service
- Signature verification logic in webhook_api.py
- process_webhook_event idempotency + user upsert path
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import uuid
from urllib.parse import urlparse

import requests


def sign(payload: str, secret: str, timestamp: int) -> str:
    signed = f"{timestamp}.{payload}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python send_test_webhook.py <webhook_url> <whsec>", file=sys.stderr)
        return 2

    url = sys.argv[1]
    whsec = sys.argv[2]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print(f"invalid url: {url}", file=sys.stderr)
        return 2

    event_id = f"evt_test_{uuid.uuid4().hex[:16]}"
    session_id = f"cs_test_{uuid.uuid4().hex[:16]}"
    customer_id = f"cus_test_{uuid.uuid4().hex[:10]}"
    sub_id = f"sub_test_{uuid.uuid4().hex[:10]}"
    user_id = str(uuid.uuid4())

    event = {
        "id": event_id,
        "object": "event",
        "api_version": "2024-06-20",
        "created": int(time.time()),
        "type": "checkout.session.completed",
        "livemode": False,
        "pending_webhooks": 1,
        "request": {"id": None, "idempotency_key": None},
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "mode": "subscription",
                "status": "complete",
                "payment_status": "paid",
                "customer": customer_id,
                "customer_email": "smoketest@example.com",
                "subscription": sub_id,
                "metadata": {"user_id": user_id, "email": "smoketest@example.com"},
                "client_reference_id": user_id,
            }
        },
    }

    payload = json.dumps(event, separators=(",", ":"))
    ts = int(time.time())
    sig = sign(payload, whsec, ts)

    print(f"POST {url}")
    print(f"  event.id   = {event_id}")
    print(f"  user_id    = {user_id}")
    print(f"  Stripe-Signature = {sig}")

    resp = requests.post(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": sig,
            "User-Agent": "local-smoketest/1.0",
        },
        timeout=30,
    )
    print(f"\nstatus={resp.status_code}")
    print(f"body={resp.text[:500]}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
