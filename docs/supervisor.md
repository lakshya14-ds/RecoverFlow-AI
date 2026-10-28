# P1 supervisor and specialists (Milestone 1)

A deterministic supervisor queues bounded specialist tasks per case. Selection
is a pure function of stored state (stage, evidence, uncertainty, payment
state, staff decisions): the same case always yields the same next task.

## Specialists and contracts

`intake`, `investigation`, `reconciliation`, `resolution`, `communication`,
`verification` — see `app/services/specialists.py`. Every output carries
case ID/version, source IDs, claim IDs, confidence, uncertainty, proposed
action, reason, and escalation conditions; outputs that violate the contract
are rejected and the task fails closed. Each specialist has an explicit tool
allowlist enforced by the tool gateway. There are deliberately no tools for
posting ledger entries, reversing, accepting evidence, sending messages,
granting approvals, approving credits, or waiving balances — model output may
classify and draft wording only. In M1 the model is used for classification;
wording stays a deterministic server template (multilingual wording is M4).

## Durability

Tasks persist in `supervisor_tasks` (migration `20261029_supervisor_v3`):
state, dependencies, attempts, idempotency key, input/result, error,
timestamps, case version, and audit history. Supported: pause, resume, bounded
retries (default 3), per-task time and model-call budgets, and replay after a
restart (`recover_interrupted_tasks` runs at startup and re-queues `running`
rows). A task whose case fingerprint changed is recorded `stale`, never
applied, and the case is reassessed fresh. Duplicate triggers are idempotent
per case version; duplicate uploads per upload ID.

## Completion and escalation (single place)

`COMPLETION_RULES` / `ESCALATION_RULES` in `app/services/supervisor.py`:
closed cases complete; blocked cases (`NEEDS_REVIEW`, `CONTACT_PAUSED`)
belong to staff; a passed verification on the current version means steady.
Retry exhaustion, specialist escalation, contract/tool violations, and
ambiguous matches fail or escalate with contact held and an audit trail.

## Triggers and API

Reassessment triggers: new document, customer reply, verified payment,
credit, reversal, and staff decisions (dispute/evidence review, resume,
approvals). Tenant-scoped API under `/api/v1/supervisor`: reassess, per-case
and tenant-wide task history, pause/resume/retry/run, and run-due. A
background loop executes due tasks; every specialist side effect is internal
(same paths the intake worker and draft flows already use automatically).

## Honesty notes

Staff dispute-review and resume supersede older proposed drafts to `stale`
(the freshness check would 409 them anyway), so verification does not fail
forever on drafts nobody will touch. Automatic triggers never supersede:
a new reply invalidating an old draft must stay visible until staff reviews.

Specialist selection is deterministic rules, not model reasoning. Verification
re-derives balances from stored rows and checks links, draft freshness, and
claim states — it does not prove real-world correctness. Evaluation of any
multi-agent advantage is M5 work with measured evidence.
