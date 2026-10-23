# Release 3: controlled agent pilot

RecoverFlow can now propose a next action, summarize recent case messages, prepare routine reply wording, and perform bounded internal actions. The selected model is **Gemini 3.8 Flash** (`gemini-3.8-flash`). The local API key reached this model's metadata endpoint. A synthetic generation check returned HTTP 503 because the model reported high demand, so a successful live generation call remains unverified. Failed calls produce labelled rules-based wording; the app does not present fallback text as model-generated.

## Control model

1. An admin opts in per tenant on **Controlled Agent**. The policy starts disabled. The admin chooses hourly assessment, automatic internal actions, daily assessment and action limits, and a maximum INR balance for automatic collection drafts.
2. A staff member can request an assessment for a case. The worker also scans cases hourly if the tenant enables that option. A hash of the ledger balance, case flags, recent conversation, and draft states prevents repeated proposals for an unchanged case.
3. Server rules select `no_action`, `staff_review`, `reply_draft`, or `collection_draft`. Gemini may write the summary, rationale, and a routine acknowledgement draft. It cannot select tools, change permissions, post ledger entries, generate payment links, update Shopify, or send a customer message.
4. Before any action, RecoverFlow compares the current case with the saved proposal snapshot. Changed balances, new messages, opt-outs, disputes, and changed draft state invalidate the proposal. Staff request a new assessment.
5. The only automatic actions are a clearly labelled internal case note and a collection draft. They require the tenant policy, a daily budget, and fresh case checks. A collection draft is never sent automatically; the existing Collections approval and send controls still apply.
6. For a routine inbound WhatsApp question, the agent prepares a reply draft. Staff can edit and explicitly send it. The Release 2 Meta configuration, 24-hour service window, triage, opt-out, and idempotency checks apply. With WhatsApp unconfigured, sending is blocked.
7. Every assessment, policy change, internal action, rejection, and staff-approved send writes an audit event. Provider payments and Shopify balances keep their Release 2 verification and staff confirmation gates.

## Setup

1. Add `GEMINI_API_KEY` to the local `.env` or deployment secret store and leave `AGENT_MODEL=gemini-3.8-flash`. Do not put the key in the UI, logs, source control, or chat. [Google's model identifier](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) and [structured output API](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) document this integration.
2. Restart the API and worker to load the new settings, endpoints, and database tables.
3. In **Controlled Agent**, enable the policy with small daily limits. First use manual assessments, inspect summaries and proposed actions, and reject incorrect ones. Then enable the hourly scan. Only enable automatic internal actions after reviewing sample outputs and the retailer's collection rules.
4. Test a paid case, an opted-out case, an open dispute, a Shopify balance mismatch, a recent customer question, an overdue receivable, and a changed balance after an assessment. Confirm that no customer message is sent and no payment entry is posted by the agent.

## Known limits before production

- The local key was verified against the Gemini model endpoint. A synthetic generation request reached the provider but returned HTTP 503 during temporary high demand; retry a live sandbox generation check before claiming model-generated summaries work. Fake-provider tests verify request shape, structured parsing, and server-side action controls. A failed model call disables automatic execution for that assessment.
- Rules-only mode provides a usable demo without a key, but its extractive summary is not a semantic AI summary.
- WhatsApp is unconfigured in the supplied status. The agent prepares replies, but staff cannot send through Meta until that account is connected. No proactive WhatsApp template campaign is implemented.
- The local API-key identity and SQLite database remain a pilot architecture. A multi-store production deployment needs managed identity, tenant-scoped secrets, database migrations, backups, monitoring, and operational review of model outputs.
- Customer messages sent to Gemini may contain personal data. Enable model calls only after the retailer approves that data flow and sets its retention and access policy. The service sends bounded case facts and recent messages, not provider credentials.
