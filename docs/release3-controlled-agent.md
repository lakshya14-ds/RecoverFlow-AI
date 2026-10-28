# Release 3: controlled agent pilot

RecoverFlow can now propose a next action, summarize recent case messages, prepare routine reply wording, and perform bounded internal actions. The selected model is **Meta Muse Spark** (`muse-spark-1.3` via the Meta Model API). The local API key was verified against Meta's API endpoint, with live generation, classification, and image/PDF extraction returning structured JSON output. Client-side rate limiting enforces configured quotas: 15 Requests Per Minute (RPM) over a 60-second sliding window and 1,500 Requests Per Day (RPD) resetting at midnight UTC. When rate limits are reached or upstream reports high demand (HTTP 429), RecoverFlow safely falls back to rules-based wording tagged with `model_rate_limited` or `model_unavailable`.

## Control model

1. An admin opts in per tenant on **Controlled Agent**. The policy starts disabled. The admin chooses hourly assessment, automatic internal actions, daily assessment and action limits, and a maximum INR balance for automatic collection drafts.
2. A staff member can request an assessment for a case. The worker also scans cases hourly if the tenant enables that option. A hash of the ledger balance, case flags, recent conversation, and draft states prevents repeated proposals for an unchanged case.
3. Server rules select `no_action`, `staff_review`, `reply_draft`, or `collection_draft`. Muse Spark may write the summary, rationale, and a routine acknowledgement draft. It cannot select tools, change permissions, post ledger entries, generate payment links, update Shopify, or send a customer message.
4. Before any action, RecoverFlow compares the current case with the saved proposal snapshot. Changed balances, new messages, opt-outs, disputes, and changed draft state invalidate the proposal. Staff request a new assessment.
5. The only automatic actions are a clearly labelled internal case note and a collection draft. They require the tenant policy, a daily budget, and fresh case checks. A collection draft is never sent automatically; the existing Collections approval and send controls still apply.
6. For a routine inbound WhatsApp question, the agent prepares a reply draft. Staff can edit and explicitly send it. The Release 2 Meta configuration, 24-hour service window, triage, opt-out, and idempotency checks apply. With WhatsApp unconfigured, sending is blocked.
7. Every assessment, policy change, internal action, rejection, and staff-approved send writes an audit event. Provider payments and Shopify balances keep their Release 2 verification and staff confirmation gates.

## Setup

1. Add `META_MODEL_API_KEY` (or `META_API_KEY_1..3`) to the local `.env` or deployment secret store and configure `AGENT_MODEL=muse-spark-1.3`, `META_RPM_LIMIT=15`, and `META_RPD_LIMIT=1500`. Do not put the key in the UI, logs, source control, or chat. [Muse Spark](https://dev.meta.ai/models/muse-spark) and the [Meta Model API](https://dev.meta.ai/products/meta-model-api) document this integration.
2. Restart the API and worker to load the new settings, endpoints, and database tables.
3. In **Controlled Agent**, enable the policy with small daily limits. First use manual assessments, inspect summaries and proposed actions, and reject incorrect ones. Then enable the hourly scan. Only enable automatic internal actions after reviewing sample outputs and the retailer's collection rules.
4. Test a paid case, an opted-out case, an open dispute, a Shopify balance mismatch, a recent customer question, an overdue receivable, and a changed balance after an assessment. Confirm that no customer message is sent and no payment entry is posted by the agent.

## API HTTP Status Codes and Error Semantics

- **`HTTP 409 Conflict`**: Policy disabled (`Controlled agent is not enabled`), case state changed after proposal snapshot (`Case changed; request a new agent assessment`), unapproved draft send attempt, or proposal not eligible for execution/rejection.
- **`HTTP 429 Too Many Requests`**: Daily agent budget exceeded (`Daily agent assessment limit reached` or `Daily internal action limit reached`). The hourly worker automatically backs off on 429.
- **`HTTP 403 Forbidden`**: Role write restriction (viewer role attempting policy updates or case assessments).
- **`HTTP 404 Not Found`**: Case or proposal not found in current tenant (strict tenant isolation).
- **`HTTP 422 Unprocessable Entity`**: Policy limit validation failure (`max_assessments_per_day` or `max_internal_actions_per_day` must be between 1 and 100).
- **`HTTP 503 Service Unavailable`**: Provider unconfigured (e.g., Meta WhatsApp unconfigured when staff attempts to send reply).

## Known limits before production

- The local key was verified against the Meta model endpoint on 2026-10-28: live classification, structured generation, and image/PDF extraction all returned shaped output. Fake-provider tests verify request shape, structured parsing, and server-side action controls. A failed model call disables automatic execution for that assessment.
- Rules-only mode provides a usable demo without a key, but its extractive summary is not a semantic AI summary.
- WhatsApp is unconfigured in the supplied status. The agent prepares replies, but staff cannot send through Meta until that account is connected. No proactive WhatsApp template campaign is implemented.
- The local API-key identity and SQLite database remain a pilot architecture. A multi-store production deployment needs managed identity, tenant-scoped secrets, database migrations, backups, monitoring, and operational review of model outputs.
- Customer messages sent to Meta may contain personal data. Enable model calls only after the retailer approves that data flow and sets its retention and access policy. The service sends bounded case facts and recent messages, not provider credentials.
