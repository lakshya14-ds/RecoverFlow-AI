# P2 gap matrix — code as source of truth (2026-10-29, Muse Code)

> **Verified update, 2026-10-30 (Codex):** final isolated suite 342 passed after
> seven fixes. See [the verification report](verification-2026-10-30.md) for the
> current 17-workstream table, commands, defects and external blockers. The
> “Existing”, “Missing” and “Test plan” bullets below preserve the original
> planning baseline; each Status describes subsequent implementation. Local
> implementation is not a production-completion claim.

Baseline verified this session: `py -3.12 -m pytest -q --disable-warnings` → **158 passed**
(57.9s); `scripts/demo_p1_showcase.py` → all beats pass in-tree (writes nothing);
`scripts/demo_hero.py` → passes in `%TEMP%\p2-baseline-demo` copy only
(30/30 split, 10/10 triage, 5/10 review; tracked eval files untouched). Tree: only
`M .codex/handoff.md` over `4f28ad6`. Port-8002 live app untouched. Money rule for all
new fields: integer minor units in storage, `Decimal` at boundaries; cash receipt,
credit adjustment, disputed, and outstanding stay distinct; every tenant-owned row and
lookup carries and enforces business identity.

## A1. Database operations — DONE on SQLite (11 tests); PostgreSQL UNVERIFIED (no instance)

- Existing: `migrate()` in `app/database/migrations.py` with `REVISIONS` + `schema_revisions`
  table, PG advisory lock, SQLite money rebuild with FK check, PG upgrade loop, idempotent
  re-entry. PG path already skips SQLite-only init (`db_manager.init_db` branches).
- Missing: migration-status endpoint; PG execution proof; backup/restore procedure + drill;
  transaction and constraint tests; supported-PG-version doc.
- Files: `app/database/migrations.py`, `app/database/db_manager.py`, `app/api/system.py`,
  `docs/ops-backup.md` (new), `tests/test_p2_a1_db.py` (new).
- Dependencies: none.
- Test plan: status lists applied/pending; re-migrate idempotent; unique/FK violations roll
  back; SQLite backup → restore roundtrip on an isolated DB (data + revisions intact).
- External input: a PostgreSQL test instance before any PG-verified claim.
- Status: done on SQLite. PG: code present, never executed — honestly unverified.

## A2. Tenant isolation — DONE (15 tests; audit + per-tenant secrets/webhooks/AFIS)

- Existing: `tenant_id` on ~all models; per-route scoping + 404-on-mismatch is the norm
  (route heatmap: every DB-touching route file references `tenant_id`); tenant-scoped unique
  constraints; AFIS file limitation already documented.
- Missing: systematic audit of all 20 route files + services + jobs + file reads + public
  webhooks (all three public callbacks hard-reject any `tenant_id != "local"` — safe but
  single-tenant; replace with per-tenant secret lookup); per-tenant provider secrets (all
  provider credentials are global settings today); AFIS transfer tenant binding; negative
  tests for cross-tenant read/write, guessed IDs, event replay, file access. Known leak:
  `frontend/evidence/*.pdf` is served unauthenticated via the static mount — must move to
  private storage (see C2).
- Files: `app/api/*`, `app/services/*`, `app/database/models.py` (secret store),
  `tests/test_p2_a2_tenancy.py` (new).
- Dependencies: A1 (migration for new tables).
- Test plan: negative tests on every surface above; secrets never in responses/logs.
- External input: none.
- Status: done. Legacy LangGraph orchestrator stays local-only by design.

## A3. Production authentication — DONE (9 tests; throttle, recovery, rotation, matrix)

- Existing: `User`/`UserApiKey`/`UserSession`, PBKDF2-HMAC-SHA256 310k iterations, login /
  logout / users / keys CRUD, 3 roles, viewer read-only middleware, key expiry + revocation,
  hashes never returned. `require_admin` used only inside `auth.py`; `require_editor` /
  `require_viewer` unused anywhere.
- Missing: login throttling; account recovery; session rotation endpoint (+ revoke-all);
  role/permission matrix doc; stronger checks wired into provider config, export/deletion,
  payment approval, message approval.
- Files: `app/auth.py`, `app/api/auth.py`, `app/services/auth_security.py`,
  `docs/auth-permissions.md` (new), route files for role wiring, `tests/test_p2_a3_auth.py`.
- Dependencies: A1 (attempt/recovery tables).
- Test plan: throttle blocks bursts; recovery + rotation flows; per-endpoint role matrix.
- External input: none (recovery via admin-issued token; no email dependency).
- Status: done. Export/deletion endpoints stay admin-only when built (F1/C2).

## A4. Team operations — DONE (12 tests; assignment, notes, tasks, SoD)

- Existing: `app/services/action_queue.py` derives one next action per case (read-only);
  `ClarificationTask` has owner/due date; approvals and audit events are immutable.
- Missing: assignment, staff notes, escalation deadlines + overdue handling, workload views,
  separation of duties (creator ≠ approver on sensitive actions), before/after records.
- Files: `app/database/models.py`, `app/services/team_ops.py` (new), `app/api/team.py` (new),
  approval endpoints for SoD, `tests/test_p2_a4_team.py` (new).
- Dependencies: A1, A3 (actor identity + roles).
- Test plan: reassign; overdue escalation fires; SoD conflict blocked; immutable history.
- External input: none.
- Status: done, including the lone-operator SoD rule.

## B1. Business identity — DONE (12 tests; GSTIN, branches, merges)

- Existing: `Counterparty` (name/type/email/phone/address/tax_id, unique per tenant);
  staff-approved `PayerAlias` matching.
- Missing: legal/display names, GSTIN field + format validation (never treated as verified
  identity), branches, billing/shipping addresses, external accounting IDs, explainable
  duplicate suggestions, staff-confirmed merge with history, cross-tenant merge block.
- Files: `app/database/models.py`, `app/services/counterparties.py` (new),
  `app/api/counterparties.py` (new), import matching, `tests/test_p2_b1_identity.py` (new).
- Dependencies: A1, A2 (tenant guard), D1 (matching use).
- Test plan: GSTIN accept/reject; merge confirm/history/invoice preservation; merge-block cases.
- External input: accountant review before any identity-verification claim (advisory only).
- Status: done. GSTIN is format-only by design; no verification claim made.

## B2. Indian document model — DONE (15 tests; lines, GST, notes, 6 fixtures)

- Existing: invoice header with tax/total, line items inside `extraction_json` (unpersisted),
  pure `line_matching` comparison, investigation + competing explanations, credit entries
  that are never cash.
- Missing: persisted line items, GST components (CGST/SGST/IGST), delivery challans,
  debit notes, freight/returns/scheme as linked documents, alleged-vs-accepted separation at
  document level, six fixtures (partial delivery, returns, wrong GST basis, freight dispute,
  scheme discount, credit-note-not-cash).
- Files: `app/database/models.py`, `app/services/vision_extraction.py`,
  `app/services/intake_pipeline.py`, `app/services/line_matching.py`,
  `app/services/investigation.py`, `tests/test_p2_b2_documents.py` (new).
- Dependencies: A1, B1 (party link); CBIC invoice/challan rules + e-invoice schema check first.
- Test plan: each fixture reconciles exactly; differences explained, never silently netted.
- External input: CBIC/e-invoice docs (web); accountant validation before tax-compliance claims.
- Status: done. CBIC Rule 46 + e-invoice schema verified from official pages; compliance claims still blocked on accountant.

## B3. Installment lifecycle — DONE (12 tests; schedules, waterfall, reversal reopen)

- Existing: `PromiseToPay` lifecycle (alleged/confirmed/kept/broken/reminders, nonfinancial);
  negotiation ladder computes instalments without persisting them.
- Missing: installment schedules with per-leg due date/amount/status/terms/approval history;
  payment→installment allocation without double counting; late/missed/reschedule/cancel/
  reversal handling; schedule-vs-ledger display split.
- Files: `app/database/models.py`, `app/services/promises.py` or `schedules.py`,
  `app/services/receivables.py`, `app/api/*`, `tests/test_p2_b3_installments.py` (new).
- Dependencies: A1, P1 allocation logic.
- Test plan: partial→installment; no double count; reschedule/reversal; promise never closes.
- External input: none.
- Status: done. Schedules are nonfinancial (approval ≠ posting); waterfall oldest-due-first
  across active schedules; reversals un-apply with history preserved and reopen derived
  `completed` schedules; late (due passed) vs missed (30+ days) computed at read time;
  creation/approval under SoD. Fixed along the way: `reverse_entry` now passes
  `reversal_of_id` (was NULL) and `unapply_entry` flushes before re-query under
  `autoflush=False`. See `docs/installments.md`.

## C1. Customer response page — DONE (12 tests; scoped tokens, safe summary, page)

- Existing: none — customer input arrives via staff-recorded replies or WhatsApp inbound.
- Missing: single-invoice scoped page; short-lived revocable single-purpose access; safe
  summary only (no notes, other invoices, staff identities, secrets); dispute submit →
  staff review + investigation/supervisor trigger; evidence attach; payment reference as
  unverified claim; rate limits; expiry behavior.
- Files: `app/database/models.py`, `app/services/portal.py` (new), `app/api/portal.py` (new),
  minimal frontend page, `tests/test_p2_c1_portal.py` (new).
- Dependencies: A1, A2, B2, C2.
- Test plan: guessed IDs, expiry, scope escape, claim-not-cash, dispute→investigation.
- External input: link host choice (default: backend origin; no blocker).
- Status: done. Single-invoice tokens (72h, revocable, 410 on expiry, 403 on
  revoke/tamper); 60/token + 200/IP + 20-guess limits per 15min; summary holds
  only the customer's bill + own submissions; disputes/payrefs/evidence enter
  staff review via the shared recording path; ledger untouched by every portal
  action. See `docs/portal.md`.

## C2. Document security — DONE (10 tests; quarantine, holds, retention, hashing)

- Existing: magic-byte validation, MIME/extension match, 10MB cap, ASCII filenames, UUID
  storage outside web root, tenant-scoped download with path-containment check, upload audit.
- Missing: SHA-256 content hash, malware-scan/quarantine workflow, retention policy,
  download access log, deletion/hold handling; migrate `frontend/evidence/*` to private
  storage (public today).
- Files: `app/database/models.py`, `app/api/intake.py`, `app/services/intake_pipeline.py`,
  seed/frontend references, `tests/test_p2_c2_documents.py` (new).
- Dependencies: A1.
- Test plan: traversal, forged type, oversized, cross-tenant, quarantined-attach block.
- External input: AV engine choice (default: scanner interface + quarantine-until-clear).
- Status: done. Shared validator (double-extension + sniffing, archives refused);
  SHA-256 on all new files with 409 on tamper and backfill for legacy rows;
  quarantine (any staff) / release (admin) / hold / soft-delete / dry-run-first
  purge; per-read access log. Honest limit: no AV engine — `clean` means
  policy-passed or staff-released, recorded in `scanned_by`. See
  `docs/document-security.md`.

## D1. Accounting connectors — DONE generic rails (12 tests); vendor e2e BLOCKED on export

- Existing: `generic_csv` mapping/preview/confirm, idempotent writer, conflict-raise (nothing
  partial), staff auth, import audit.
- Missing: first-system choice; mapping contract, dry run, reconciliation report,
  cursor/checkpoint, idempotency keys, conflict queue, provenance; e2e for chosen system.
- Files: `app/services/import_adapter.py`, `app/api/imports.py`, `tests/test_p2_d1_import.py`.
- Dependencies: A1?, C2 (export file upload).
- Test plan: contract tests on sanitized fixtures (blocked); synthetic generic_csv e2e.
- External input: sanitized export + product/version + sample docs from the pilot business.
- Status: done for the generic path. Import runs (idempotency keys, source hash,
  payload/cursor/report provenance), conflict queue with staff resolution,
  reconciliation totals that add up. Strict all-or-nothing confirm kept.
  Vendor e2e (Tally/BUSY/Zoho) stays blocked: no export received, unknown
  profiles rejected by the API. See `docs/accounting-import.md`.

## D2. Real payment integration — DONE mock-tested (15 tests); sandbox/live BLOCKED

- Existing: `configured()` + test/live key-match validation, link create/cancel/recover by
  reference, HMAC webhook verify, dedup `ProviderEvent` with body-hash mismatch detection,
  captured/amount/currency checks, refund/dispute → `needs_review` + case suppression,
  partial-paid status, `rzp_test_mock` path.
- Missing: explicit disabled-by-default live gate (live works today if keys are set — must
  gate); settlement matching; refund/chargeback ledger-reversal path (currently flag-only);
  discrepancy-queue API; out-of-order/stale-event tests; test/live label separation.
- Files: `app/services/razorpay.py`, `app/api/webhooks.py`, `app/api/payments.py`,
  `tests/test_p2_d2_payments.py` (new).
- Dependencies: A1 (settlement/discrepancy tables), E (webhook worker).
- Test plan: adverse sandbox-model tests (dup, bad sig, stale, partial settlement, refund,
  reversal-after-post) against mocks; no real charge.
- External input: Razorpay test-account access for sandbox verification; live needs explicit
  authorization + account.
- Status: done against mocks. Disabled-by-default live gate (API + webhooks);
  test/live/mode labels on events, links, and a per-tenant status endpoint;
  payment.failed recording; refund/chargeback discrepancy queue with
  staff-confirmed reversals; settlement matching with short/unmatched queue;
  out-of-order-safe (refund-first parks, reversal refused until posted).
  Sandbox verification and any live use stay blocked as before. Honest
  status: mock-tested, sandbox-pending, live disabled. See
  `docs/live-payments.md`.

## D3. Real communication — DONE sandbox (11 tests); live send disabled by design

- Existing: WA inbound signed+dedupe+phone-match+suppression+opt-out keywords; gated
  `send_reply`; dunning drafts + exact-version approvals; `EMAIL_DRY_RUN=true` default;
  contact flags.
- Missing: template registry; consent basis; suppression management; quiet hours; language
  prefs; delivery/failure tracking; replies→lifecycle routing; email equivalents.
  (Per-business config landed in A2; the 24h window is already enforced on the
  sandbox-reply API.)
- Files: `app/services/meta_whatsapp.py`, `app/api/messages.py`, `app/api/dunning.py`,
  `app/database/models.py`, `tests/test_p2_d3_comms.py` (new).
- Dependencies: A1/A2 (per-tenant config + secrets), E.
- Test plan: window block, template/quiet-hour/opt-out enforcement, failure queue.
- External input: WABA + email accounts + onboarding; provider-rule check before build.
- Status: done in sandbox. Template registry (draft/approve/archive, strict
  vars, guard re-check), per-invoice consent + language, quiet hold/release
  (IST), delivery receipts via statuses[], triage refactored onto the shared
  lifecycle path. Live stays off: per-channel toggles default false,
  non-local live 503, no email send endpoint, no SMTP library. Provider
  statuses[] shape verified against current Cloud API docs. See
  `docs/comms-policy.md`.

## E. Reliable workers and operations — DONE (15 tests; leases, DLQ, metrics, runbook)

- Existing: intake atomic claim (`UPDATE … WHERE queued` + rowcount), supervisor
  retries/`max_attempts`/crash recovery/replay/audit, bounded loops with clean shutdown.
- Missing: supervisor multi-worker claim audit, leases/heartbeats, dead-letter queue +
  operator replay API, poison-message handling, backoff policy, metrics endpoint
  (queue depth/age, failures, provider errors, model cost/latency, delivery, unreconciled
  settlements, allocation gaps), alerts, operator runbook.
- Files: `app/services/supervisor.py`, `app/services/intake_pipeline.py`, `app/main.py`,
  `app/api/system.py`, `docs/runbook.md` (new), `tests/test_p2_e_workers.py` (new).
- Dependencies: A1 (DLQ/job metadata).
- Test plan: simultaneous workers, crash-after-claim, lease expiry, replay, poison.
- External input: none.
- Status: done. Atomic conditional-UPDATE claims + 5-minute leases +
  heartbeats + deterministic backoff + poison dead-lettering (3 unexpected
  crashes) for intake and supervisor; operator retry/dismiss APIs; webhook
  duplicate convergence; metrics + 8 alert rules with owners/severities;
  runbook. Honest gaps: model cost untracked (no pricing), alerts are pull,
  single-tenant ops view. See `docs/runbook.md`.

## F1. Privacy readiness — workflows tested; legal review pending

- Existing: synthetic-only fixtures, `ProviderEvent` stores body hash (no PII), no secrets
  in audit/logs/handoff, sandbox isolation.
- Missing: personal-data inventory, notices, access/export/correction/deletion workflows,
  retention holds, incident-response runbook, legal review.
- Files: `docs/privacy.md` (new), subject-request API + service, `tests/test_p2_f1_privacy.py`.
- Dependencies: A3 (roles for export/delete), C2 (retention/deletion).
- Test plan: export/delete/hold flows on synthetic data.
- External input: MeitY DPDP rules check (web); legal review before any compliance claim.
- Status: admin access/export/correction/deletion implemented in `app/api/privacy.py`
  and `app/services/privacy.py`, migration v18; 13 tests including explicit-party
  identity isolation. Retention blocks and ledger preservation tested. Limited
  erasure scope; compliance claims remain blocked on legal review.

## F2. Real-world validation — BLOCKED on external input

- Existing: 30-case + 38-case eval harnesses, demo scripts, honest-limits documentation.
- Missing: everything requiring real humans — interviews, consented pilot, measured recovery.
- Files: `docs/validation-plan.md` (protocol + evidence-trail templates only).
- Dependencies: all prior (pilot-ready app).
- Test plan: N/A — disclose sample size/selection limits; never invent outcomes.
- External input: participating businesses + consent + access.
- Status: protocol and measurement templates written; execution blocked on
  participating businesses, consent, access and accountant review. No measured
  pilot results or willingness-to-pay evidence.

## F3. Economics — report tested; full metering and market evidence incomplete

- Existing: per-slot RPM/RPD usage counters, `SupervisorTask.model_calls`, latency measured
  in evals.
- Missing: persisted usage/cost ledger, per-case/per-business rollups, comms/storage/infra/
  support cost inputs, willingness-to-pay evidence, unit-economics report with
  measured-vs-assumed split + sensitivity scenarios.
- Files: `app/services/meta_agent.py` instrumentation, `app/database/models.py`,
  reports, `docs/economics.md` (new), `tests/test_p2_f3_economics.py` (new).
- Dependencies: E (metrics), D2/D3 (fee inputs).
- Test plan: metering accuracy, report math on synthetic usage.
- External input: real fee schedules (web-knowable); WTP interviews (blocked).
- Status: `app/services/economics.py` and admin `/system/economics` report
  measured usage, explicit price assumptions, computed costs and pending inputs;
  six tests pass with production ledger signs. Gross payment volume is positive;
  reversal counts stay separate. Intake/vision calls remain uninstrumented,
  usage is not a complete billing ledger, and price/market claims remain blocked.
