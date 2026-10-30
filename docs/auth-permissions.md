# Roles and permission matrix (P2 A3)

Three roles, enforced in this order: the API middleware rejects unauthenticated
calls (401) and blocks every non-GET call from `viewer` (403); sensitive
endpoints additionally require `admin` (403 otherwise).

| Capability | viewer | editor | admin |
| --- | --- | --- | --- |
| Read cases, evidence, queues, reports | yes | yes | yes |
| Record replies, triage messages, manage drafts | no | yes | yes |
| Approve customer-facing message versions | no | yes + SoD | yes |
| Confirm invoices, resolve explanations/clarifications | no | yes | yes |
| Post manual payments/credits | no | no | yes |
| Reverse entries | no | no | yes |
| Approve allocation proposals / reconciliations | no | no | yes |
| Confirm uploaded receipts (posts payment) | no | no | yes |
| Manage users, API keys, provider secrets/settings | no | no | yes |
| Issue recovery tokens, read migration status | no | no | yes |
| Data export / deletion (F1, when built) | no | no | yes |

SoD = separation of duties (P2 A4): the staff member who created a draft may
not approve it. Exact-version approval and server-side re-verification apply to
every role. Static bootstrap keys and `RECOVERFLOW_API_KEYS_JSON` entries carry
an explicit role and tenant; database users and API keys carry their own.

## Login hardening

- Throttle: 5 failures per email or 20 per IP within 15 minutes → 429. A
  successful login clears the email count. Attempts older than 24h are pruned.
- Recovery (no email dependency): an admin issues a single-use 1-hour token
  (`POST /auth/users/{id}/recovery`, same tenant only); the holder redeems it
  at public `POST /auth/recover`. Redemption sets the password and revokes all
  of the user's sessions. Raw tokens are shown once and stored hashed.
- Sessions: `POST /auth/rotate` swaps the current token; `GET /auth/sessions`
  lists metadata only; `DELETE /auth/sessions/{id}` revokes one;
  `POST /auth/revoke-all` and `POST /auth/logout` end sessions. API keys have
  no sessions and cannot rotate.

## Operator notes

- Throttle state lives in `login_attempts`; inspect per-email/IP counts there
  when staff report lockouts. Do not export this table (see `docs/privacy.md`).
- Recovery tokens live hashed in `user_recovery_tokens`; an issued token that
  never redeems simply expires. Re-issue rather than reusing.
- Keep bootstrap keys in the server environment only; prefer per-user database
  accounts so revocation and audit stay precise.
