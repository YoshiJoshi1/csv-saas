# Deployment Runbook

## Architecture

- Streamlit Cloud runs `app.py`
- Separate web service runs `webhook_api.py`
- Both share the same Postgres `DATABASE_URL`

## 1) Provision managed Postgres

- Create Postgres instance (Supabase/Render/Railway or equivalent).
- Copy connection string into `DATABASE_URL`.

## 2) Configure Supabase Auth

- Create Supabase project.
- Enable Email/Password provider.
- Set:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`

## 3) Deploy webhook API service

- Deploy a Python web service with entry command:
  - `uvicorn webhook_api:app --host 0.0.0.0 --port $PORT`
- Set env vars:
  - `DATABASE_URL`
  - `STRIPE_SECRET_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `LOG_LEVEL=INFO`

## 4) Configure Stripe

- Create product/price and copy `STRIPE_PRICE_ID`.
- Set checkout redirect URLs:
  - `STRIPE_SUCCESS_URL` -> Streamlit app URL
  - `STRIPE_CANCEL_URL` -> Streamlit app URL
- Configure webhook endpoint:
  - `https://<webhook-api-domain>/stripe/webhook`
- Subscribe to events:
  - `checkout.session.completed`
  - `checkout.session.async_payment_succeeded`
  - `invoice.paid`
  - `invoice.payment_failed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`

## 5) Deploy Streamlit app

- Deploy repo with `app.py` entrypoint.
- Set env vars:
  - `DATABASE_URL`
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `STRIPE_SECRET_KEY`
  - `STRIPE_PRICE_ID`
  - `STRIPE_SUCCESS_URL`
  - `STRIPE_CANCEL_URL`
  - `LOG_LEVEL=INFO`

## 6) Run migrations

- Initial schema:
  - `alembic upgrade head`
- Legacy SQLite import (optional):
  - `python migrate_legacy_sqlite.py`
  - dry run: `python migrate_legacy_sqlite.py --dry-run`
