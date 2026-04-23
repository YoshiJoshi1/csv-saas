# Operations and Data Retention

## Logging and Monitoring

- Monitor webhook API `/health`.
- Monitor Stripe webhook delivery logs for non-2xx responses.
- Alert on repeated 5xx responses from `/stripe/webhook`.

## Data Retention

- User entitlement data (`users` table) is retained while account is active.
- Webhook idempotency records (`processed_webhook_events`) are retained for auditability.
- Uploaded CSV content is processed in-memory by default and not persisted.

## Data Deletion Requests

On verified request, remove by user ID/email:

1. Delete entitlement row from `users`.
2. Remove related logs/events where operationally allowed.
3. Confirm deletion request completion to user.

## Backup and Recovery

- Enable daily managed Postgres backups.
- Perform quarterly restore test to validate backup integrity.
- Document RPO/RTO in your hosting provider settings.

## Incident Response

1. Triage severity (billing/auth data issues are high priority).
2. Revoke affected credentials/keys if secrets are suspected exposed.
3. Patch and redeploy.
4. Backfill any missed webhook events from Stripe event history.
