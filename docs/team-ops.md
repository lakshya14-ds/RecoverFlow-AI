# Team operations (P2 A4)

Staff coordination around cases: ownership, notes, tasks, escalations,
workload, and separation of duties on approvals. All endpoints live under
`/api/v1/team/*` and are tenant-scoped; writes need editor or admin.

## Assignment

`POST /team/cases/{id}/assign {"assignee_user_id", "reason"}` sets the owner.
History is insert-only: `GET .../assignments` shows every handover, and each
change writes an audit row with before/after owner and reason. Only active
users of the same tenant can be assigned.

## Notes

`POST /team/cases/{id}/notes {"body"}` appends an internal note. Notes have no
edit or delete path — a correction is a new note — so the case record stays
append-only. Notes are staff-internal and never exposed to customers (see the
portal scope in the C1 design when it lands).

## Tasks

`POST /team/tasks` creates an internal task with an optional case link,
assignee, and due date. `.../complete`, `.../cancel`, and `.../reassign`
(with reason) move it; completion records who acted. Overdue is computed at
read time (`due_date < today`, still open).

## Escalations

`POST /team/cases/{id}/escalations {"reason", "deadline"}` raises a concern.
`POST /team/escalations/sweep` flips past-deadline open rows to `escalated`
and flags their cases for human review; run it on a schedule or on demand.
`POST /team/escalations/{id}/resolve` closes one. Open escalations surface
first in the owner queue (`GET /api/v1/supervisor/queue`).

## Workload

`GET /team/workload` returns per-assignee open tasks, overdue tasks, assigned
cases, and open escalations, sorted with the hottest load first. Escalations
on unassigned cases count under `unassigned`.

## Separation of duties

The creator of a sensitive action cannot approve it: allocation approvals
(vs proposal creator), agent-draft approvals (vs version editor), dunning
approvals (vs draft author — staff triggers and edits now stamp authorship),
and negotiation approvals (vs turn actor). Violations return 409 naming the
conflict. Solo-operator tenants (fewer than two active users) proceed with a
`sod_skipped_lone_operator` audit note instead of deadlocking; use personal
logins (not one shared key) so the check can tell people apart.
