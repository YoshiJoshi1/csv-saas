# Streamlit CSV Cleaning SaaS

Production-oriented Streamlit SaaS app with:

- Supabase Auth-based user identity
- Stripe Checkout + webhook-driven entitlements
- Managed Postgres support via `DATABASE_URL`
- Streamlit frontend + standalone FastAPI webhook API

## Quick start (local)

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Run one-click local startup:
   - `start-dev.bat`
3. Run tests:
   - `pytest -q`

## Required environment variables

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_PRICE_ID`
- `STRIPE_SUCCESS_URL`
- `STRIPE_CANCEL_URL`
- `STRIPE_WEBHOOK_SECRET`

Optional:

- `MAX_UPLOAD_MB`
- `MAX_UPLOAD_ROWS`
- `MAX_UPLOAD_COLUMNS`
- `MAX_WEBHOOK_BODY_KB`
- `SENTRY_DSN`
- `SENTRY_TRACES_SAMPLE_RATE`
- `LOG_LEVEL`

## Deployment

See:

- `docs/DEPLOYMENT.md`
- `docs/OPERATIONS.md`
- `docs/PRIVACY.md`
- `docs/TERMS.md`
