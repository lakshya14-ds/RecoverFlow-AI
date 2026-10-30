# Business identity (P2 B1)

Counterparties identify the buyers and vendors behind invoices. Fields follow
the e-invoice party naming (`LglNm` legal name, `TrdNm` trade/display name,
`Gstin`, addresses) so a future e-invoice mapping stays natural.

## Parties, branches, external IDs

- `POST /api/v1/counterparties` creates a customer or vendor with optional
  legal/display names, GSTIN, billing/shipping addresses, and tax ID.
- Branches (`.../{id}/branches`) model business locations. Same-state
  branches may legitimately share the HQ GSTIN, so branch GSTINs are
  format-checked but never uniqueness-blocked.
- External IDs (`.../{id}/external-ids`) link one party to its identities in
  Tally, BUSY, Zoho, Shopify, or other systems (`system` + `external_id`,
  unique per business). No vendor format is inferred — see D1.

## GSTIN rule

GSTIN validation is FORMAT-ONLY: 15 characters (2-digit state code 01–38,
10-character PAN, entity code, `Z`, checksum character), normalized to
uppercase. A syntactically valid GSTIN is unique per business but is NOT
verified identity — registry/checksum verification is future work and no
identity-verification claim may rest on this check.

## Duplicates and merges

- `GET .../{id}/duplicates` scores same-business candidates with reasons
  (same email/phone, name similarity). GSTIN and tax ID cannot duplicate
  (uniqueness-enforced), so they never appear as merge reasons.
- Merging is staff-confirmed and admin-only: preview first
  (`POST .../{id}/merge-preview`), then
  `POST .../{id}/merge {"winner_id", "reason"}`. The merge moves invoice,
  branch, and external-ID links to the winner, marks the loser `merged`, and
  writes an immutable `counterparty_merges` row plus audit. Invoice name
  fields are NEVER rewritten. Cross-tenant, self, and already-merged merges
  are rejected.
- `POST /api/v1/counterparties/bootstrap {"invoice_type"}` onboards history:
  it creates parties from distinct unlinked invoice names and links them
  (idempotent; AR creates customers, AP creates vendors). Accounting imports
  link new rows to an exact-name party automatically.
