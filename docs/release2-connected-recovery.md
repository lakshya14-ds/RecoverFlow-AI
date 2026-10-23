# Release 2: connected recovery pilot

The selected pilot stack is **Shopify + Razorpay + Meta WhatsApp Cloud API**, for retailers in India collecting INR credit-term receivables. This checkout contains the integration code and local tests. The provider accounts have not been connected, so no live payment link or WhatsApp message can be created yet.

## What the code does

1. **Shopify:** `POST /api/v1/sync/shopify` reads up to ten pages of orders via the GraphQL Admin API. Only payment schedules with an INR balance and a due date become receivable cases. External payment schedule IDs prevent duplicate imports. A worker scans one page every five minutes and follows a saved cursor for larger stores. Signed order webhooks are deduplicated; new orders are fetched by ID, while paid, changed, or cancelled orders pause matching cases until staff reviews the balance. An admin can use **Cases → Confirm Shopify case** after the local ledger matches Shopify; contact stays paused until a separate documented resume. Shopify is read-only: RecoverFlow does not write to orders or issue refunds.
2. **Razorpay:** Staff use **Cases → Create payment link** for an eligible INR balance. The link expires after seven days and is created with provider notifications disabled, so staff choose when to share it. The full-balance link has a local idempotency key and a Razorpay reference ID. Signed `payment_link.paid` or `payment_link.partially_paid` callbacks verify a captured payment, link ID, amount, and currency before posting an immutable receivable entry. Duplicate callbacks do not double post. Unknown links, excess amounts, or ambiguous payments remain in **Provider events needing review**. An admin can cancel a link in Razorpay or document resolution of an exception from the dashboard; marking an event reviewed never posts money by itself.
   For a Shopify case, any verified Razorpay payment pauses contact and requires staff to reconcile the Shopify balance with RecoverFlow. Shopify stays read-only. After updating or confirming the balance in Shopify, an admin uses **Confirm Shopify case** and then the separate resume action if further contact is appropriate.
3. **WhatsApp:** Meta callback verification and signed message webhooks feed **Connected Recovery → WhatsApp inbox**. An incoming text pauses matching cases, and a clear STOP message sets opt-out immediately. Staff assign and classify the message. A staff-written reply can be sent through Cloud API only within 24 hours of the inbound message; a timed-out send stays unresolved to avoid duplicate retries. Proactive collection templates are not enabled until the retailer approves them and Meta approves the template.
4. **Policy schedule:** Admins can opt in to daily draft creation, choose an IANA timezone and overdue thresholds, and run the local worker. Eligibility checks skip paid, disputed, opted-out, paused, or recently contacted cases. Drafts still require staff approval and a separate send action.

## Connection steps

1. Create the provider accounts and a dedicated test store. In Shopify, obtain a store domain ending in `.myshopify.com` and an Admin API token with order and payment-term read access. Customer contact fields may require additional protected customer data approval. Add order webhook subscriptions and obtain the app webhook secret. [Shopify Admin GraphQL](https://shopify.dev/docs/api/admin-graphql/2026-07), [webhook verification](https://shopify.dev/docs/api/webhooks/2026-07), [payment schedules](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/PaymentSchedule).
2. Create Razorpay test API keys and a separate webhook secret. Subscribe the public callback to `payment_link.paid`, `payment_link.partially_paid`, `payment_link.cancelled`, `payment_link.expired`, `refund.processed`, and relevant payment dispute events. A refund or dispute pauses the case for staff ledger review; it does not automatically reverse an entry. Keep `RAZORPAY_MODE=test` until a complete test run is approved. [Payment Link API](https://razorpay.com/docs/api/payments/payment-links/create-standard/), [webhook validation and event IDs](https://razorpay.com/docs/webhooks/validate-test/).
3. Create a Meta app and WhatsApp Business account with a phone number ID, access token, app secret, and webhook verify token. Subscribe to the `messages` webhook. Obtain approved collection templates before using proactive WhatsApp outreach; this pilot only supports staff replies to an inbound conversation. [Meta's WhatsApp API collection](https://www.postman.com/meta/whatsapp-business-platform/documentation/wl), [messages endpoint](https://www.postman.com/meta/whatsapp-business-platform/folder/o48mro7/messages).
4. Expose RecoverFlow behind a public HTTPS host and register these exact callbacks: `/api/v1/webhooks/shopify/local`, `/api/v1/webhooks/razorpay/local`, and `/api/v1/webhooks/meta-whatsapp/local`. Provider services cannot call `127.0.0.1`. Authenticate staff APIs with `X-RECOVERFLOW-API-KEY`; callbacks use their own provider signatures.
5. Add the values below to the local `.env` or a deployment secret store. Do not put credentials in the dashboard, tests, source control, or chat. Restart the API and worker after changing them.

```dotenv
SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_ACCESS_TOKEN=
SHOPIFY_API_VERSION=2026-07
SHOPIFY_WEBHOOK_SECRET=
RAZORPAY_MODE=test
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
META_WHATSAPP_ACCESS_TOKEN=
META_WHATSAPP_PHONE_NUMBER_ID=
META_WHATSAPP_APP_SECRET=
META_WHATSAPP_VERIFY_TOKEN=
META_GRAPH_API_VERSION=
```

6. In test mode, import a Shopify order with payment terms, inspect the receivable, create a Razorpay link, pay it using Razorpay's test flow, and check that exactly one ledger entry appears. Repeat the webhook and verify the balance does not change. Send an inbound WhatsApp test message, confirm the case pauses, triage it, and test a staff reply. Enable the draft policy only after checking the retailer's approved stage timing and contact rules.

## Operational boundaries

- Credentials are environment scoped to the `local` pilot tenant. Multi-store credential isolation and OAuth onboarding are not implemented.
- A Shopify balance difference, cancellation, or payment event pauses the case for staff review. RecoverFlow does not infer a write-off or post an external Shopify payment without a unique verified payment reference.
- A manual payment or credit makes an existing Razorpay link unresolved because its amount may be stale. An admin should cancel that link in Razorpay before creating another. If creation timed out, **Check Razorpay** searches by its reference ID without creating a second link. An uncertain WhatsApp send is not retried automatically.
- Refund and dispute callbacks pause affected cases for review but do not automatically reverse a payment. Webhook replay after secret rotation, abandoned payment links, WhatsApp media, delivery status tracking, and approved outbound template campaigns still need provider-account test cases before production use.
- SQLite and API keys are appropriate for local pilot testing. A multi-user deployment needs database migrations, stronger identity and permissions, backups, monitoring, reconciliation operations, HTTPS termination, and an audit review process.
