# Sharing approval workflow

## Set up n8n Cloud

1. Make `POST /partners/heatfix/connector/jobs` reachable from n8n Cloud over HTTPS. For a local demo, put a tunnel in front of an authenticated proxy that forwards only that method and path to FastAPI. Configure the proxy to require a random secret in `X-HeatFix-Demo-Secret`. If the tunnel URL changes, update the HeatFix URL in n8n.
2. Import `sharing-approved.json` using **Import from File** in the n8n workflow editor. In **Create or reuse HeatFix job**, set the HTTPS URL from step 1. For the proxy setup, choose **Generic Credential Type** → **Header Auth** and configure `X-HeatFix-Demo-Secret` with the proxy's secret. [n8n import guide](https://docs.n8n.io/build/manage-workflows/export-and-import/)
3. In **Sharing approved**, attach a separate **Header Auth** credential with header name `X-N8N-Webhook-Secret` and an independently generated secret. Publish the workflow and copy the webhook's **Production URL**.

## Connect FastAPI

Set `N8N_CASE_WEBHOOK_URL` to the workflow's production URL in `backend/.env`. Set `N8N_WEBHOOK_SECRET` to the secret from **Sharing approved**, then restart FastAPI and check `GET /api/health`. Keep the webhook and proxy secrets in their local settings and n8n credentials. With `N8N_CASE_WEBHOOK_URL` empty, FastAPI dispatches directly to HeatFix.

## Backend contract

1. After persisting approval, FastAPI sends `event: maintenance.sharing_approved`, `case_id`, and `order`. The `order` follows the [shared connector v1 fixture](../shared/fixtures/partner-job.json) and contains only the partner fields covered by the approval. Its `request_id` equals `case_id`, and its `idempotency_key` stays stable across attempts.
2. n8n forwards `order` to `POST /partners/heatfix/connector/jobs`. HeatFix returns the same `job_id` for the same key, including after a restart.
3. n8n returns `case_id`, `job_id`, and `duplicate`. FastAPI checks the case ID and records the first confirmed job. If the acknowledgment is missing or invalid, FastAPI returns `502`, keeps the approval, and allows the same approval request to be retried.

## Smoke test

With FastAPI and HeatFix running, create a synthetic case using the [case fixture](../shared/fixtures/case-create.json). Confirm there is no HeatFix job until you approve sharing using the [approval fixture](../shared/fixtures/sharing-approval.json). Confirm the approval response contains `partner_job_id`. Replay the same authenticated webhook payload and compare its `job_id` with the original. Check `GET /partners/heatfix/connector/jobs` for exactly one job for the case. When using the webhook **Test URL**, select **Listen for test event** before each request. [n8n Webhook guide](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/)
