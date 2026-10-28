# P1 evidence-led investigation (Milestone 2)

Line-level comparison lives in `app/services/line_matching.py` (pure, no
database, no model). It compares normalized SKU aliases, units, quantities,
unit prices, tax basis, freight, and rounding across invoice, purchase order,
delivery note, return note, agreed discount, and customer message lines.

## Rules that are never silent

- Unit conversion happens only on exact match or a staff-approved `unit_rules`
  row. Any other mismatch pauses the case and opens a clarification task.
- Tax and freight are never apportioned automatically. A variance becomes a
  `tax_basis_difference` hypothesis only with positive evidence (the invoice
  states tax, the variance equals that tax exactly, and the other total plus
  tax equals the invoice total); otherwise it is a price difference.
- A scheme-discount hypothesis appears only when a scheme line matches the
  variance on the same item. Overlapping claim types on one item always need
  staff allocation.
- Sub-cent remainders require an explicit rounding/tax decision.

## Competing explanations

When sources disagree (or two evidenced hypotheses fit), the investigator
stores a `competing_explanations` row with supporting and contradicting source
references per hypothesis and pauses contact. Staff pick one hypothesis via
`POST /cases/{id}/explanations/{eid}/resolve` with a reason; picking never
moves money — the dispute-review path still sets the amount. Runs that no
longer conflict mark untouched open explanations superseded.

## Clarification tasks

When one missing fact blocks a decision (readable copy, unit rule, tax/freight
allocation, SKU attribution, damage evidence), the investigator opens a
`clarification_tasks` row with owner, source, due date (+7 days), affected
amount, and an **unsent** draft preview. No send path exists: the preview is
text on the row, and fulfilling links the new evidence, which triggers
reassessment. Short supply, damaged goods, returns, price differences, and
scheme discounts are covered; damage stays an allegation until evidenced.

## Stage separation

Customer text is an allegation, parsed fields are extracted, staff
confirmations are verified, dispute decisions are accepted, and only the
authorized posting paths create ledger entries. Accepting evidence alone never
posts; tests pin each transition and the distinct artifacts.
