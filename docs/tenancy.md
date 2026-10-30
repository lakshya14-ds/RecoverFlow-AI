# Tenant isolation model (P2 A2)

Every tenant-owned row carries `tenant_id`, and every lookup enforces it: list
queries filter by the caller's tenant, single-row reads return 404 on mismatch
(never 403, so IDs cannot be probed), and writes stamp the caller's tenant.
Jobs and workers are tenant-agnostic executors — they always act through the
job's, policy's, or invoice's own tenant.

## Surfaces and status

| Surface | Enforcement |
| --- | --- |
| All 20 API route files | `tenant_id` filter or 404-on-mismatch; audited line by line, incl. two hardened invoice-review lookups |
| Intake uploads + file download | Tenant-scoped rows; path containment under the intake store |
| Evidence doc fixtures | `GET /cases/{id}/evidence-files/{name}`: tenant invoice + name must match the tenant's own evidence row + docs-tree containment. The old public `frontend/evidence/*.pdf` copies are deleted; the UI fetches through the API with the staff key |
| Provider webhooks | Tenant from the URL slug (validated); signature verified with that tenant's secret; unknown tenant → 503, malformed slug → 404, replay with a changed body → 409 |
| AFIS transfers | Per-tenant database file (`afis_db_path` setting); `local` falls back to the global path. Allocation, unmatched listing, and the reconciliation specialist all resolve per tenant |
| Provider credentials | Stored by reference only (`TenantSecret`: `env:NAME` / `file:/path`); values never enter the DB, responses, logs, or fixtures. Admin-only management |
| Non-secret provider config | `TenantSetting` allowlist (AFIS path, Razorpay mode/key, WhatsApp phone id, Shopify domain); validated on write |
| Legacy LangGraph path | Keeps its `local`-only AFIS gate until retired; all live paths are per-tenant |

## Operating per-tenant credentials (admin)

1. Put the real value in the environment or a root-only file, e.g.
   `TENANT_ACME_RZP_HOOK` or `/run/secrets/acme-rzp-hook`.
2. `POST /api/v1/integrations/secrets` with
   `{"provider": "razorpay", "name": "webhook_secret",
     "secret_ref": "env:TENANT_ACME_RZP_HOOK", "label": "acme store"}`.
3. `GET /api/v1/integrations/secrets` shows the pointer and whether it
   currently resolves — never the value.
4. Rotate by changing the env/file value; nothing in the database changes.
   Remove with `DELETE /api/v1/integrations/secrets/{provider}/{name}`.

`local` keeps working from the existing global settings, so the pilot database
needs no reconfiguration. Production should move the referenced values into a
managed vault/KMS later; the pointer model already supports that migration.

## Webhook onboarding per business

1. Store the provider's webhook secret as above.
2. Set non-secret config: `PUT /api/v1/integrations/settings`
   (e.g. `meta_whatsapp_phone_number_id`, `shopify_shop_domain`).
3. Give the provider the tenant-bound URL:
   `/api/v1/webhooks/razorpay/{tenant}`, `/api/v1/webhooks/shopify/{tenant}`,
   `/api/v1/webhooks/meta-whatsapp/{tenant}`.
4. Events land under that tenant only; cross-tenant replay is rejected by the
   `(tenant, kind, provider, event_id)` key plus body-hash comparison.
