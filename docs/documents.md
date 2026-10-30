# Indian document model (P2 B2)

Document fields follow the CBIC invoice particulars (Rule 46) and the
notified e-invoice schema (`HsnCd`, `Qty`, `UnitPrice`, `AssAmt`, `GstRt`,
`CgstAmt`/`SgstAmt`/`IgstAmt`). Verified against the official CBIC and
e-invoice pages on 2026-10-29. No tax-compliance claim is made — an Indian
accountant must review the design before any such claim.

## What is persisted

- **Invoice lines** (`invoice_line_items`): SKU, description, HSN, quantity,
  unit, unit price, taxable amount, GST rate, and per-line CGST/SGST/IGST.
  Intake persists them as **alleged** from validated extraction; staff can
  record or correct lines (`POST /cases/{id}/line-items`) as **verified**
  when extraction cannot reconcile (e.g. tax-inclusive line pricing).
- **Invoice tax split**: CGST/SGST/IGST, freight, and round-off cents on the
  invoice. Intake requires an extracted CGST+SGST+IGST split to reconcile to
  the tax total when all three are printed.
- **Credit/debit notes** (`credit_debit_notes`): number, date, amount, GST
  split, reason, source upload. Lifecycle: `alleged` → `staff_accepted` →
  `posted` (or `cancelled`). Acceptance needs a second staff member when the
  business has one (SoD); posting is admin-only and creates the ledger entry
  through `post_entry` (idempotent; double-post returns the same entry).
  An alleged note never touches cash, credits, or the dispute.
- **Supporting documents**: delivery challans, freight bills, and scheme
  letters linked to the invoice with source upload and summary.

## Ledger meaning

- A posted **credit** note reduces outstanding and increases credits; cash
  received never moves. A posted **debit** note increases outstanding above
  the original face and is reported separately as `debits`.
- Debit notes post without allocation (fresh, undisputed debt). Reversing a
  debit restores the prior outstanding. The consistency rule is
  `0 <= disputed <= outstanding <= face + debits`.

## Investigation behavior

- Persisted lines drive matching when present; extraction lines remain the
  fallback for older uploads.
- Delivery challans behave like delivery notes; scheme letters behave like
  discount agreements; freight bills compare against invoice freight and
  hold the case on difference.
- Quantity shortfalls on taxed lines still require a staff tax/freight
  decision — the system never apportions tax by itself — but the
  clarification now states the exact lines, GST rates, splits, and invoice
  freight the decision must cover.
