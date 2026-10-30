# Independent verification and hardening - 2026-10-30

Agent: Codex. Scope: P0 foundations, P1 M1-M5, P2 A-F, repository documentation and an isolated application run. Existing uncommitted work was preserved. No commit, push, live payment, customer send, or live model call was performed. Port 8002 and its database were never opened or changed.

## Result and evidence boundary

The final suite passed **342 tests**, up from 337 existing tests plus five new regression tests. Seven defects were corrected. This establishes the tested local behavior, not universal correctness, production readiness, provider certification or legal compliance.

CodeRabbit was unavailable: its official installer reported `Unsupported operating system: mingw64_nt-10.0-26300`. The user explicitly requested continuing without it. No result here is attributed to CodeRabbit.

## Commands and results

The requested `py -3.12` launcher was unavailable on PATH. The equivalent installed interpreter was `C:\Users\Lakshya Arora\Documents\anaconda\python.exe`, reporting Python 3.12.7. In the commands below, `$python` denotes that exact executable.

Test processes set `DATABASE_URL` empty, `APEX_DB_PATH` to `%TEMP%\recoverflow-verify-bootstrap.db`, and all four Meta key variables empty. Individual tests also create isolated fixture databases. The source copy excluded `.env`, all `*.db*`, data, backups and caches.

| Check | Exact invocation / method | Result |
| --- | --- | --- |
| Baseline | `& $python -m pytest -q --disable-warnings` | 334 passed, 3 failed; 171 warnings; 113.90 s |
| New service regressions before fixes | Two new foundations tests, new privacy identity test, and `tests/test_p2_f3_economics.py`, with `-q --disable-warnings --tb=short` | 5 failed, 4 passed; wrong signs and identity/reversal behavior reproduced |
| First fix group | `& $python -m pytest tests/test_foundations.py tests/test_p2_b2_documents.py tests/test_p2_b3_installments.py tests/test_p2_f1_privacy.py tests/test_p2_f3_economics.py tests/test_release1.py::test_existing_schema_gains_release_one_columns tests/test_release2.py::test_release2_tables_and_columns_migrate_existing_database tests/test_workflow.py::test_legacy_unique_date_migrates_for_tenants -q --disable-warnings --tb=short` | 76 passed; 23 warnings; 37.25 s |
| Worker regressions before fixes | `& $python -m pytest tests/test_p2_e1_workers.py -k 'startup_recovery or background_tick' -q --disable-warnings --tb=short` | Both new tests failed |
| Worker fix group | `& $python -m pytest tests/test_p2_e1_workers.py tests/test_p1_supervisor.py tests/test_intake_uploads.py -q --disable-warnings --tb=short` | 30 passed; 96 warnings; 22.91 s |
| Final full suite | `& $python -m pytest -q --disable-warnings --tb=short` | **342 passed**, 177 warnings; 113.82 s |
| Showcase | `& $python scripts/demo_p1_showcase.py` in-tree | Passed; final INR 4,000 dispute remains after SIMULATED INR 56,000 payment |
| Hero | `& $python scripts/demo_hero.py` in isolated source copy | Passed; 30/30 split, 10/10 routing, 5/10 review without entry; INR 30,000 disputed remains |
| P1 evaluation rerun | `& $python scripts/run_p1_evaluation.py` in isolated source copy | Completed all 38 cases across three arms; zero model calls; measured shortcomings retained below |
| Frontend syntax | `node --check frontend/app.js`, `node --check frontend/portal.js`, `node --check frontend/config.js` | Passed |
| Whitespace | `git diff --check` | Passed; Git emitted line-ending notices, not whitespace errors |
| SQLite backup/restore and migration checks | `tests/test_p2_a1_db.py` within final suite | Passed, including restore drill and legacy upgrade |

Warnings were not converted into failures. The run reports an unset pytest-asyncio fixture-loop-scope warning and existing deprecation warnings; this report does not claim a warning-free suite. Concurrency assertions were not relaxed and no load-dependent failure occurred during this verification.

The fresh P1 rerun reproduced the published behavioral scores: held-out requested
amounts were 9/28 rules, 22/28 single, 20/28 specialist; held-out escalation was
22/28, 28/28, 22/28 respectively. Adversarial requests were 3/15, 14/15, 12/15;
adversarial unsafe-action counts were 1, 0, 0. Single and specialist tied on
dispute correctness (28/28 held-out, 15/15 adversarial) and allocation (24/24,
14/14). Invoice-unit denominators exceed case counts where fixtures contain
multiple invoices. These are retained benchmark limitations, not failing pytest
assertions and not an assertion that all collection decisions are correct.
Five checkout evaluation files were SHA-256 identical before/after the showcase
and final isolated evaluations; published reports were not overwritten.

## Defects fixed

| Defect | Before | Correction and regression evidence |
| --- | --- | --- |
| Migration bootstrap connection | Three tests migrated a temporary engine, then `init_db()` queried `users` through the unrelated default `SessionLocal`, failing against a blank default database. | Bootstrap binds to the same engine just migrated. The three unchanged migration tests now pass without an existing pilot DB. |
| Reversal ceiling ignored debit notes | An INR 1,000 invoice plus INR 200 debit, followed by INR 100 payment, could not reverse that payment back to INR 1,200 outstanding. | Reversal ceiling includes net debit adjustments; original-entry, amount and duplicate guards remain. New regression proves cash returns to zero and the debit stays outstanding. |
| Reversal retry ignored original identity | Reusing a reversal reference with a different same-amount original payment returned the old reversal as success. | Idempotent reversal retry must reference the same original entry. Same-original retry succeeds; changed-original retry fails. |
| Privacy name match overrode explicit identity | Export/deletion selection could include another counterparty's explicitly linked invoice when names matched. | Name fallback applies only to unlinked legacy invoices. A new test checks export isolation, deletion eligibility and preservation of the other customer's contact fields. |
| Economics used signed receipt amounts as volume | Real ledger payments are negative, so gross volume and percentage fee estimates became negative. Existing economics fixtures had the signs reversed. | Gross volume negates the payment ledger sign. Fixtures now follow the real sign convention; existing exact-volume and INR 46.00 fee assertions fail before and pass after the fix. Reversals remain separately reported. |
| Startup reset active leases | Starting another application process reset every running/processing job, even one leased by a live worker. | Startup only recovers legacy unleased rows. Active leases remain owned; expired leases use normal atomic claims. New regression covers both intake and supervisor. |
| Supervisor did not pick up expired leases | Its background loop selected only queued jobs, so an expired running job could remain stuck until restart. | The loop includes expired running tasks and lets the atomic claim determine ownership. A new regression executes the recovered task once with attempts incremented to two. |

Changed application files: `app/database/db_manager.py`, `app/services/receivables.py`, `app/services/privacy.py`, `app/services/economics.py`, `app/services/supervisor.py`, `app/services/intake_pipeline.py`. Tests changed in foundations, P2 E1, F1 and F3. Existing agents' edits were retained.

## Claim checks: P0 and P1

- **Money paths:** imports, intake confirmation, manual entries, allocation, reconciliation and provider events use Decimal or integer minor units and the shared posting service for AR money movement. Foundation tests exercise precision, negative amounts, overpayment, currency mismatch, cash versus credits, allocation and reversals. This does not make the adjustment log double-entry accounting.
- **Lifecycle and trust:** seven stages are defined in `case_lifecycle.py`. Tests cover paid versus adjusted closure, stale approvals, nonfinancial promises/drafts, trust review metadata and migration of old verified flags without promotion to accepted. Historical unverifiable allocations still need staff reconciliation.
- **Supervisor:** six named specialists, output contracts, allowlisted tools, deterministic selection, durable tasks, budgets and tenant gates are implemented. Tests cover stale results, forbidden tools, retries, pause/resume, crash recovery and atomic claims. No arbitrary financial-action tool is exposed to the model.
- **Investigation:** tested invoice/PO/line comparisons, competing hypotheses, missing unit/tax/freight clarification, damage/returns and unsent drafts. This is bounded synthetic evidence coverage, not a real-document accuracy guarantee.
- **Allocation and promises:** tests cover split transfers, multiple transfers, ambiguity holds, tenant/currency bounds, idempotency, reversals and nonfinancial promise state. AFIS remains a file integration; it is not a verified bank feed.
- **Communication and imports:** EN/HI/Hinglish structured draft checks and exact-version approvals are tested. Generic CSV preview/confirm/run/conflict flows are tested; named accounting-vendor formats are not implemented or verified.
- **Evaluation:** the 38-case runner forces model access off. Its rules baseline, single pass and specialist workflow are comparisons of deterministic orchestration, not measured live Meta reasoning. Published failures and sample-size limits remain material; no advantage claim is justified merely by having multiple specialists.

## P2: all 17 workstreams

“Verified” below means local synthetic tests and code-path checks, not field validation.

| Workstream | Status | Evidence / precise limit |
| --- | --- | --- |
| A1 Database operations | SQLite verified; PostgreSQL unverified | v1-v18, zero pending on isolated server, legacy upgrades, constraint tests, backup/restore drill; needs PG instance and driver. |
| A2 Tenant isolation | Tested for covered routes | Tenant-bound APIs, secrets by reference, provider events and private evidence; legacy orchestrator remains local-only. |
| A3 Authentication | Implemented and tested locally | Throttle, recovery, sessions, rotation and role tests; static bootstrap keys remain supported. |
| A4 Team operations | Implemented and tested | Assignments, notes, tasks, escalation, workload and audit; lone-operator SoD exception is explicit. |
| B1 Counterparty identity | Implemented and tested | Branches, external IDs, duplicates and merges; GSTIN is format-only, not registry verification. |
| B2 Indian documents | Implemented and tested on fixtures | GST splits, notes, delivery/return/freight/scheme handling; no accountant compliance validation. |
| B3 Installments | Implemented and tested | Partial waterfall applications, reschedules, cancellation, payment reversals and history. |
| C1 Customer portal | Implemented and tested | Single-invoice tokens, expiry/revocation/rate limits and claims-only submissions. |
| C2 Document protection | Implemented and tested; AV absent | Type/magic-byte/hash checks, private access, quarantine/holds/retention; staff release is not an antivirus scan. |
| D1 Accounting connectors | Generic rails verified; vendor blocked | Needs sanitized pilot export, accounting product/version and matching sample documents. |
| D2 Payments | Mock-tested; external sandbox unverified | Live gate remains off; signatures, event duplication, refunds and settlements covered by mocks. Needs Razorpay test account and callback setup. |
| D3 Communication | Sandbox tested; live disabled | Templates, consent, quiet hours and delivery statuses; no live email endpoint or threadless campaigns. Needs provider test setup before any external test. |
| E1 Workers | Tested, with recovery fixes | Atomic claims, expiry pickup, retries/backoff, poison/dead-letter/replay; no general distributed exactly-once guarantee. |
| E2 Operations | Implemented and tested locally | Counts/ages, eight pull-alert rules and runbook; no push alert delivery or load/soak validation. |
| F1 Privacy | Workflows tested; legal review pending | Admin export/correction/deletion, identity scoping and holds; retains books/audit and has limited erasure scope. |
| F2 Real-world validation | Protocol ready; execution blocked | No pilot participants, consent, access, interviews or measured recovery. |
| F3 Economics | Report tested; metering partial | Measured/assumed/pending sections and corrected payment signs; no intake/vision call metering or willingness-to-pay evidence. |

## Isolated app and UI QA

The flow under test was: app loads, authenticate with a synthetic key, open the hero case, inspect balance/evidence, open Control, and navigate from its owner queue back to the case.

The server ran from `%TEMP%\verify-demo-codex-20261030` on `http://127.0.0.1:8138` with a separate `smoke.db`, no copied `.env`, and no provider credentials. Health, authenticated case, privacy list and economics returned 200. Migrations returned `20261113_privacy_v18`, 18 applied, no pending or unknown revisions. A bad staff key returned 401; an export for an unknown subject returned 400. The hero split was 240000 / 150000 / 90000 / 30000 / 60000 INR. A supervisor reassessment completed resolution, communication and verification, producing the INR 60,000 draft and an approval queue item without posting money.

The legacy Browser skill was unavailable. Regular Playwright could not launch Edge (`TargetClosedError`); its Chromium binary was absent. The available in-app browser then completed the UI checks through computer-use controls.

| UI check | Result |
| --- | --- |
| URL/title and meaningful content | Correct port-8138 RecoverFlow page; Intake, Review and Control rendered |
| Framework error overlay | None observed |
| Console errors/warnings | None captured in the inspected flows |
| Desktop | 1440 x 900 Control view; document width 1425, no horizontal overflow |
| Mobile | 390 x 844; document width 375; queue, activity and case navigation worked without horizontal overflow |
| Interaction | Open file, Control navigation, populated queue and Open case all produced the expected state |
| Visual evidence | Desktop and mobile screenshots inspected in-session; no frontend source changes needed |

This was targeted smoke QA, not exhaustive UI interaction coverage. Automated API suites cover the financial and approval actions; this browser pass did not repeat all upload/edit/send/portal workflows.

A final fresh-database smoke on port 8139 ran the updated source after worker
fixes. It repeated health/case/privacy/economics, 18 migrations with zero pending,
and the 401/400 checks, and asserted positive gross receipt volume of 15,000,000
paise from the seeded negative payment entry. Both owned servers were stopped;
their smoke databases and the temporary default test database were removed.

## Remaining inputs and risks

- **PostgreSQL:** provide a disposable PG 15+ instance, suitable test credentials through a private configuration channel, and the psycopg driver before migration/transaction claims.
- **Accounting vendor:** provide a sanitized export, product/version, field meanings and corresponding invoice/receipt examples. Generic CSV alone does not prove vendor support.
- **Provider validation:** Razorpay test-account configuration and webhook routing; WhatsApp test business/number/templates/consent setup. Current task did not authorize live activation or customer sends.
- **Pilot:** named participating businesses, reviewed consent, read-only access, staff time logs and an accountant reviewer. Never place customer data in fixtures, demos or this repository's handoff.
- **Legal/tax:** qualified review of privacy/retention notices and tax document treatment. This report makes no legal deadline or compliance assertion.
- **Economics and model quality:** actual provider/hosting/support prices, complete usage instrumentation and consented willingness-to-pay interviews. A separate labeled live Meta evaluation is needed before model-benefit claims.
- **Deployment:** AV integration, HTTPS/hosting review, credential governance, operational monitoring and production load testing remain outside this verification.
- **Known bounded behavior:** legacy name-only customer records can remain ambiguous; use confirmed identity links. Synthetic keyword/template coverage does not establish robust multilingual understanding. The published P1 evaluation includes escalation/request errors and missing specialist promise extraction. Small fixture suites are not an exhaustive security or correctness proof.

The README and P2 status matrix now distinguish implemented local capabilities from mocked, incomplete and externally blocked work. Historical handoff entries are preserved and superseded by dated verification entries.
