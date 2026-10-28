# P1 showcase walkthrough plan (about 6 minutes)

Run `python scripts/demo_p1_showcase.py` from the repository root. Offline,
deterministic, isolated database; prints each beat and asserts it. It writes
no docs or frontend files. `scripts/demo_hero.py` stays the regression demo.

## Beats

1. **Evidence (0:00).** Invoice SHOW-001 for INR 100,000 with PO and delivery
   note linked; INR 40,000 received. On screen: Review view, source links.
2. **Hinglish claim (0:45).** "2 carton short aaye the, baaki payment next
   week kar dunga" recorded; language detected as Hinglish; contact pauses
   for staff triage. On screen: case messages.
3. **First draft (1:30).** Staff resumes; the supervisor chain drafts a
   Hinglish request for the undisputed INR 56,000.00 only. Unsent.
4. **Conflict (2:15).** A message claiming "5 units short" disagrees with the
   delivery note (2 units). Investigation holds the case with competing
   explanations (400,000 vs 1,000,000 cents); no amount is invented.
5. **Held payment (3:00).** An INR 60,000.00 transfer with no reference
   matches two equal outstandings; the proposal is ambiguous with zero legs
   and waits for staff. Control view: agent activity shows the tasks.
6. **Clarification (3:30).** A damage allegation creates one targeted,
   customer-owned clarification ("obtain damage evidence") with an unsent
   draft preview. Owner queue shows the next actions.
7. **Invalidation (4:00).** Approving the old draft now fails (409): new
   evidence changed the case version. Staff resolves the conflict to the
   delivery note and sets the dispute at INR 4,000.00.
8. **Approval and payment (4:45).** A fresh chain drafts at the new version;
   staff edits one sentence and approves the exact hash. A signed
   **SIMULATED** INR 56,000.00 payment posts; the case becomes
   `PARTIALLY_RESOLVED` with INR 4,000.00 still disputed, the transfer still
   held, and the damage clarification still open.

## Architecture explanation (for the recording)

One deterministic supervisor queues bounded specialist tasks (intake,
investigation, reconciliation, resolution, communication, verification) from
case stage, evidence, uncertainty, and payment state. Specialists read
through a tool allowlist; nothing posts, approves, waives, or sends except
existing staff-gated paths. Model output only classifies and rephrases
fact-free wording; amounts, dates, and dispute meaning are server-owned and
re-validated before wording, after wording, and at exact-version approval.
Tasks persist with idempotency keys, budgets, retries, and crash recovery.
See [architecture](architecture.md), [evaluation](p1-evaluation.md), and the
[owner queue](communication.md).
