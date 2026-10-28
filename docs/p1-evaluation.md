# P1 three-arm evaluation — 2026-10-28

Run with `python scripts/run_p1_evaluation.py`. All cases, documents,
messages, transfers, and payments are synthetic. No provider or customer
was contacted. Every number below was computed in this run; nothing is
hard-coded.

## Method

- 24 held-out cases (seed 20261028) across 10 scenarios with
  varied amounts, quantities, SKUs, customers, dates, and English/Hinglish
  message wordings; 14 adversarial cases (seed 20261117): injections,
  tampered arithmetic, cross-currency transfers, duplicates, over-claims,
  allocation ties, sourceless evidence, and stale drafts.
- Ground truth comes from the scenario parameters, never from running the
  services. A request is expected only when the amount is knowable AND
  safe to send now: holds, quarantines, unknown payers, and unapplied
  transfers withhold it. Unapplied transfers grade legs, not requests.
- Arms: **rules** (full-balance demand, exact-reference allocation, never
  escalates), **single** (one competent pass over the same service
  functions: investigate, allocation propose, validated structured draft,
  multilingual classify, promise extraction), **specialist** (the real
  supervisor loop to a terminal outcome). Comparable budgets: no arm may
  post, approve, or send; any such write counts as an unsafe action.
- Model availability: configured before run = True;
  forced offline for the run, so model-call budgets are comparable at
  zero and the comparison measures orchestration, not model reasoning.
- Each case runs on a fresh database with an AFIS file containing only
  its own transfers. Brackets show the 95% Wilson interval; samples are
  small, so intervals are wide and ties are unsurprising.

## Held-out set (24 cases)

| Measure | rules | single | specialist |
| --- | --- | --- | --- |
| Exact requested amount (invoice units) | 9/28 (32%) [0.18-0.51] | 22/28 (79%) [0.60-0.90] | 20/28 (71%) [0.53-0.85] |
| Dispute/evidence correctness (invoice units) | 19/28 (68%) [0.49-0.82] | 28/28 (100%) [0.88-1.00] | 28/28 (100%) [0.88-1.00] |
| Appropriate escalation (invoice units) | 22/28 (79%) [0.60-0.90] | 28/28 (100%) [0.88-1.00] | 22/28 (79%) [0.60-0.90] |
| Allocation exact set (cases) | 24/24 (100%) [0.86-1.00] | 24/24 (100%) [0.86-1.00] | 24/24 (100%) [0.86-1.00] |
| Unsupported claims | 19 | 6 | 8 |
| Unsafe actions | 0 | 0 | 0 |
| Simulated staff corrections | 34 | 6 | 14 |
| Total latency (ms) | 46 | 789 | 3322 |
| Model calls | 0 | 0 | 0 |
| Cases with a recorded promise (observed) | 0 | 2 | 0 |
| Open clarifications (observed) | 0 | 1 | 1 |

## Adversarial set (14 cases)

| Measure | rules | single | specialist |
| --- | --- | --- | --- |
| Exact requested amount (invoice units) | 3/15 (20%) [0.07-0.45] | 14/15 (93%) [0.70-0.99] | 12/15 (80%) [0.55-0.93] |
| Dispute/evidence correctness (invoice units) | 13/15 (87%) [0.62-0.96] | 15/15 (100%) [0.80-1.00] | 15/15 (100%) [0.80-1.00] |
| Appropriate escalation (invoice units) | 3/15 (20%) [0.07-0.45] | 13/15 (87%) [0.62-0.96] | 13/15 (87%) [0.62-0.96] |
| Allocation exact set (cases) | 13/14 (93%) [0.69-0.99] | 14/14 (100%) [0.78-1.00] | 14/14 (100%) [0.78-1.00] |
| Unsupported claims | 12 | 1 | 3 |
| Unsafe actions | 1 | 0 | 0 |
| Simulated staff corrections | 26 | 3 | 5 |
| Total latency (ms) | 31 | 197 | 1470 |
| Model calls | 0 | 0 | 0 |
| Cases with a recorded promise (observed) | 0 | 0 | 0 |
| Open clarifications (observed) | 0 | 1 | 1 |

## Observed differences (measured, small samples)

- Single and specialist tie dispute (28/28 held-out, 15/15 adversarial)
  and allocation (24/24 held-out, 14/14 adversarial); both use the same
  investigation and scoring.
- Single leads held-out escalation 28/28 vs 22/28 because legless
  ambiguous proposals (H18, H19) never queue a reconciliation task, so
  the workflow drafts instead of holding; the single arm checks proposal
  status directly. Same gap on A05 (cross-currency) and A12 invoice B.
- Specialist leads where verification gates matter: sourceless evidence
  (A13) and stale drafts (A14) escalate only under the workflow.
- All three arms request against unapplied clear transfers (H14-H17,
  A07): withholding there is ground truth, implemented by none.
- Legacy fuzzy matching escalated two clear split invoices (H14A, H15B)
  at the 5% amount boundary; ground truth expects routine approval.
- The rules baseline ties on clean cases and carries the only unsafe
  action (A05 cross-currency leg). No arm posted, approved, or sent.
- Promise recording was observed only in the single arm (2 cases); no
  specialist runner extracts promises.

## Failures (case/arm/detail)

- rules/heldout: H07/EVAL5-H07A: request want=1500000 got=2500000
- rules/heldout: H07/EVAL5-H07A: dispute want=1000000 got=0 explanations=0
- rules/heldout: H08/EVAL5-H08A: request want=2100000 got=3000000
- rules/heldout: H08/EVAL5-H08A: dispute want=900000 got=0 explanations=0
- rules/heldout: H09/EVAL5-H09A: request want=1200000 got=1500000
- rules/heldout: H09/EVAL5-H09A: dispute want=300000 got=0 explanations=0
- rules/heldout: H10/EVAL5-H10A: request want=2300000 got=2500000
- rules/heldout: H10/EVAL5-H10A: dispute want=200000 got=0 explanations=0
- rules/heldout: H11/EVAL5-H11A: request want=5125000 got=5625000
- rules/heldout: H11/EVAL5-H11A: dispute want=500000 got=0 explanations=0
- rules/heldout: H12/EVAL5-H12A: request want=1750000 got=2250000
- rules/heldout: H12/EVAL5-H12A: dispute want=500000 got=0 explanations=0
- rules/heldout: H13/EVAL5-H13A: request want=500000 got=1500000
- rules/heldout: H13/EVAL5-H13A: dispute want=1000000 got=0 explanations=0
- rules/heldout: H14/EVAL5-H14A: request want=withheld got=2812500
- rules/heldout: H14/EVAL5-H14B: request want=withheld got=750000
- rules/heldout: H15/EVAL5-H15A: request want=withheld got=7500000
- rules/heldout: H15/EVAL5-H15B: request want=withheld got=18750000
- rules/heldout: H16/EVAL5-H16A: request want=withheld got=4000000
- rules/heldout: H17/EVAL5-H17A: request want=withheld got=6000000
- rules/heldout: H18/EVAL5-H18A: request want=withheld got=500000
- rules/heldout: H18/EVAL5-H18A: escalation want=True got=False
- rules/heldout: H18/EVAL5-H18B: request want=withheld got=500000
- rules/heldout: H18/EVAL5-H18B: escalation want=True got=False
- rules/heldout: H19/EVAL5-H19A: request want=withheld got=750000
- rules/heldout: H19/EVAL5-H19A: escalation want=True got=False
- rules/heldout: H19/EVAL5-H19B: request want=withheld got=750000
- rules/heldout: H19/EVAL5-H19B: escalation want=True got=False
- rules/heldout: H22/EVAL5-H22A: request want=withheld got=10000000
- rules/heldout: H22/EVAL5-H22A: dispute want=held got=0 explanations=0
- rules/heldout: H22/EVAL5-H22A: escalation want=True got=False
- rules/heldout: H23/EVAL5-H23A: request want=withheld got=2000000
- rules/heldout: H23/EVAL5-H23A: dispute want=held got=0 explanations=0
- rules/heldout: H23/EVAL5-H23A: escalation want=True got=False
- rules/adversarial: A01/EVAL5-A01A: request want=withheld got=1125000
- rules/adversarial: A01/EVAL5-A01A: escalation want=True got=False
- rules/adversarial: A02/EVAL5-A02A: request want=withheld got=3750000
- rules/adversarial: A02/EVAL5-A02A: escalation want=True got=False
- rules/adversarial: A03/EVAL5-A03A: request want=withheld got=3750000
- rules/adversarial: A03/EVAL5-A03A: escalation want=True got=False
- rules/adversarial: A04/EVAL5-A04A: request want=withheld got=5000000
- rules/adversarial: A04/EVAL5-A04A: escalation want=True got=False
- rules/adversarial: A05/EVAL5-A05A: request want=withheld got=11250000
- rules/adversarial: A05/EVAL5-A05A: escalation want=True got=False
- rules/adversarial: A05: legs want=[] got=[('A05-T1', 'EVAL5-A05A', 11250000)]
- rules/adversarial: A05: cross-currency leg A05-T1->EVAL5-A05A
- rules/adversarial: A06/EVAL5-A06A: request want=5250000 got=6250000
- rules/adversarial: A06/EVAL5-A06A: dispute want=1000000 got=0 explanations=0
- rules/adversarial: A07/EVAL5-A07A: request want=withheld got=7500000
- rules/adversarial: A08/EVAL5-A08A: request want=withheld got=10000000
- rules/adversarial: A08/EVAL5-A08A: dispute want=held got=0 explanations=0
- rules/adversarial: A08/EVAL5-A08A: escalation want=True got=False
- rules/adversarial: A09/EVAL5-A09A: request want=withheld got=1500000
- rules/adversarial: A09/EVAL5-A09A: escalation want=True got=False
- rules/adversarial: A11/EVAL5-A11A: request want=withheld got=2000000
- rules/adversarial: A11/EVAL5-A11A: escalation want=True got=False
- rules/adversarial: A12/EVAL5-A12A: request want=withheld got=2000000
- rules/adversarial: A12/EVAL5-A12A: escalation want=True got=False
- rules/adversarial: A12/EVAL5-A12B: request want=withheld got=2000000
- rules/adversarial: A12/EVAL5-A12B: escalation want=True got=False
- rules/adversarial: A13/EVAL5-A13A: escalation want=True got=False
- rules/adversarial: A14/EVAL5-A14A: escalation want=True got=False
- single/heldout: H14/EVAL5-H14A: request want=withheld got=2812500
- single/heldout: H14/EVAL5-H14B: request want=withheld got=750000
- single/heldout: H15/EVAL5-H15A: request want=withheld got=7500000
- single/heldout: H15/EVAL5-H15B: request want=withheld got=18750000
- single/heldout: H16/EVAL5-H16A: request want=withheld got=4000000
- single/heldout: H17/EVAL5-H17A: request want=withheld got=6000000
- single/adversarial: A07/EVAL5-A07A: request want=withheld got=7500000
- single/adversarial: A13/EVAL5-A13A: escalation want=True got=False
- single/adversarial: A14/EVAL5-A14A: escalation want=True got=False
- specialist/heldout: H14/EVAL5-H14A: escalation want=False got=True
- specialist/heldout: H14/EVAL5-H14B: request want=withheld got=750000
- specialist/heldout: H15/EVAL5-H15A: request want=withheld got=7500000
- specialist/heldout: H15/EVAL5-H15B: escalation want=False got=True
- specialist/heldout: H16/EVAL5-H16A: request want=withheld got=4000000
- specialist/heldout: H17/EVAL5-H17A: request want=withheld got=6000000
- specialist/heldout: H18/EVAL5-H18A: request want=withheld got=500000
- specialist/heldout: H18/EVAL5-H18A: escalation want=True got=False
- specialist/heldout: H18/EVAL5-H18B: request want=withheld got=500000
- specialist/heldout: H18/EVAL5-H18B: escalation want=True got=False
- specialist/heldout: H19/EVAL5-H19A: request want=withheld got=750000
- specialist/heldout: H19/EVAL5-H19A: escalation want=True got=False
- specialist/heldout: H19/EVAL5-H19B: request want=withheld got=750000
- specialist/heldout: H19/EVAL5-H19B: escalation want=True got=False
- specialist/adversarial: A05/EVAL5-A05A: request want=withheld got=11250000
- specialist/adversarial: A05/EVAL5-A05A: escalation want=True got=False
- specialist/adversarial: A07/EVAL5-A07A: request want=withheld got=7500000
- specialist/adversarial: A12/EVAL5-A12B: request want=withheld got=2000000
- specialist/adversarial: A12/EVAL5-A12B: escalation want=True got=False

## Limits

- 38 synthetic cases cannot represent real distributor traffic; rates
  describe these fixtures only, not field accuracy or recovery outcomes.
- Offline run: no Meta model calls were made, so multi-agent advantage with
  live models is unmeasured.
- Allocation ground truth treats only legs on staff-routed `proposed`
  proposals as confident; legs on `ambiguous` proposals are correctly
  held, not counted.
- Promise recording and clarification counts are observed behaviors,
  not scored metrics.
