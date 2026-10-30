# Real-world validation plan (F2)

How RecoverFlow gets measured against real distributor work — and what
is still missing before that can start. **Status: protocol ready,
execution blocked.** No pilot business, no access, and no consent exist
yet, so this file contains zero measured numbers. Any future report
fills the templates below and never invents interviews, quotes,
recoveries, or ROI.

## 1. Entry criteria (all must hold before contact)

1. The user names 1–3 participating businesses and a contact person
   (owner or office manager) per business.
2. Written consent covers: observing collection work, using anonymized
   case counts/timings, and recording interviews (or notes-only).
   Consent text needs counsel review alongside `docs/privacy.md` §5.
3. Read-only access is agreed: sanitized accounting export + sample
   documents first; no live credentials until a later phase, if ever.
4. Synthetic-data rule: pilot data never lands in fixtures, tests, or
   demos; pilot tenants are separate databases.

## 2. Baseline metrics (definitions + where each is read from)

| # | Metric | Definition | Source |
|---|---|---|---|
| M1 | Time per case | Staff minutes from first touch to terminal state, per invoice | audit timestamps + staff log (template §5) |
| M2 | Time to undisputed amount | Hours from intake to first accepted undisputed-balance claim | `case_evidence` accepted rows |
| M3 | Staff corrections | Corrections per case (rejected proposals, edited drafts, re-allocations) | allocation/draft audit actions |
| M4 | Wrong or blocked actions | Unsafe generations blocked + staff-reported wrong actions | approval rejections, incident notes |
| M5 | Response rate | Customer replies per approved outbound message | inbound/outbound linkage |
| M6 | Verified recovery | Cash posted via the authorized path per period | `receivable_entries` kind=payment |
| M7 | Escalation rate | Cases reaching staff review vs auto-completed tasks | supervisor task outcomes |

M1 needs a staff time log — the system cannot observe desk work. M6
counts verified payments only; promises, drafts, and simulated links
are excluded by construction.

## 3. Interview protocol

- 45 minutes, owner + one collection-staff member separately.
- Fixed spine, asked verbatim: current collection process, tools,
  busiest failure mode, how a disputed bill is resolved today, what
  "done" looks like, willingness to pay for time saved (see F3).
- Notes within 24h, quotes verbatim or marked paraphrase, business
  anonymized as P1/P2/P3 in every report.
- Minimum honest sample: 3 businesses before any pattern claim; a
  single pilot supports a case study only, never a market claim.

## 4. Pilot protocol

1. Week 0: baseline — observe current process, fill M1–M7 by hand for
   10–20 live cases. No RecoverFlow in the loop.
2. Week 1–2: assisted — staff use RecoverFlow for new cases with all
   approvals on; every AI proposal needs explicit accept/edit/reject.
3. Week 3: review — compare M1–M7 against baseline on matched cases,
   collect usability failures, decide continue/stop.
4. Stop rules: any wrong customer-facing send, any ledger error, or
   staff veto ends the pilot immediately; write up what happened.

Selection limits are disclosed: convenience sample, credited businesses,
short window. The report states what the sample cannot prove.

## 5. Case-level evidence trail (template, one row per pilot case)

`pilot_id | invoice_ref (pseudonymized) | baseline_minutes |
tool_minutes | corrections | escalated? | outcome | notes`

Kept outside the repo (pilot data rule §1.4); only aggregates enter
`docs/evaluation.md`, with sample size attached.

## 6. Usability observation

Watch two full sessions per business: intake of a real bill, handling
of one ambiguous payment, approving one message. Record task success,
misclicks, help needed, and every moment staff work around the tool
instead of through it. Workarounds are findings, not user error.

## 7. Report template (fills only from §5 rows + system tables)

- Sample: businesses, cases, dates, selection method.
- Table: M1–M7 baseline vs pilot with n per cell.
- Failures: wrong/blocked actions with cause, usability issues.
- Quotes: verbatim, anonymized, with consent on file.
- Limits: what was not measured and why.
- Verdict: continue / change / stop, with the smallest next test.

## 8. Blockers (precise)

1. No participating business named — need 1–3 distributors + contacts.
2. No consent text approved — needs counsel review.
3. No baseline access — need observation time + sanitized export.
4. No accountant reviewer — needed before any tax/compliance-adjacent
   claim leaves this repo.

Until all four clear, F2 stays "protocol ready, execution blocked",
and no validation claim appears in the README or any demo.
