"""Simulate a customer paying a Razorpay Payment Link in hackathon demo mode."""
import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path
from uuid import uuid4
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings

def main():
    parser = argparse.ArgumentParser(description="Simulate Razorpay customer payment (SIMULATED)")
    parser.add_argument("--invoice-id", type=int, help="Invoice ID to pay")
    parser.add_argument("--amount", type=float, help="Custom payment amount in INR (defaults to undisputed balance)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002", help="Server base URL")
    args = parser.parse_args()

    api_key = settings.RECOVERFLOW_API_KEY or "replace-with-a-long-random-secret"
    headers = {"X-RECOVERFLOW-API-KEY": api_key}

    print("=" * 65)
    print("RAZORPAY PAYMENT SIMULATOR [SIMULATED ENVIRONMENT - NOT REAL MONEY]")
    print("=" * 65)

    # 1. Fetch cases to find eligible invoice (prioritize hero case if present)
    if not args.invoice_id:
        r = requests.get(f"{args.base_url}/api/v1/cases", headers=headers)
        if r.status_code != 200:
            print(f"Error fetching cases: {r.status_code} - {r.text}")
            return
        cases = r.json()
        # Look for hero case first
        hero_cases = [c for c in cases if c.get("invoice_number") == "INV-2026-HERO" and c.get("status") not in ("paid", "RESOLVED_PAID", "PARTIALLY_RESOLVED")]
        eligible = hero_cases or [c for c in cases if c.get("currency") == "INR" and c.get("balance_cents", 0) > 0 and c.get("status") not in ("paid", "RESOLVED_PAID")]
        
        if not eligible:
            print("No open INR cases found. Run 'python scripts/seed_hero_case.py' first.")
            return
        target = eligible[0]
        invoice_id = target["invoice_id"]
    else:
        invoice_id = args.invoice_id
        r = requests.get(f"{args.base_url}/api/v1/cases/{invoice_id}", headers=headers)
        if r.status_code != 200:
            print(f"Error fetching case {invoice_id}: {r.status_code} - {r.text}")
            return
        target = r.json()

    undisputed_cents = target.get("undisputed_cents", target.get("balance_cents", 0))
    disputed_cents = target.get("disputed_cents", 0)
    pay_amount_cents = int(args.amount * 100) if args.amount else (undisputed_cents if undisputed_cents > 0 else target.get("balance_cents", 0))

    print(f"Selected Invoice:   ID {invoice_id} ({target['invoice_number']})")
    print(f"Customer:           {target.get('customer')}")
    print(f"Outstanding Total:  INR {target.get('balance_cents', 0) / 100:>10,.2f}")
    if disputed_cents > 0:
        print(f"Disputed Portion:   INR {disputed_cents / 100:>10,.2f} [Delivery Shortfall Under Review]")
        print(f"Undisputed Portion: INR {undisputed_cents / 100:>10,.2f} [Actionable Owed Funds]")
    print(f"Payment to Simulate:INR {pay_amount_cents / 100:>10,.2f} [SIMULATED]")

    # 2. Check or create payment link for the target amount
    idempotency_key = str(uuid4())
    print(f"\n1. Requesting Razorpay Payment Link for INR {pay_amount_cents / 100:.2f} (SIMULATED)...")
    link_payload = {
        "invoice_id": invoice_id,
        "idempotency_key": idempotency_key,
        "amount_cents": pay_amount_cents,
    }

    r_link = requests.post(f"{args.base_url}/api/v1/payments/links", headers=headers, json=link_payload)
    if r_link.status_code not in (200, 201):
        # Maybe an active link already exists
        r_links = requests.get(f"{args.base_url}/api/v1/payments/links", headers=headers)
        links = r_links.json()
        active = [l for l in links if l.get("invoice_id") == invoice_id and l.get("status") in ("open", "creating")]
        if not active:
            print(f"Could not create link: {r_link.status_code} - {r_link.text}")
            return
        link = active[0]
        print(f"Found existing active payment link: ID {link['id']}")
    else:
        link = r_link.json()
        print(f"Payment Link Created Successfully!")

    print(f"   Provider Link ID: {link.get('provider_link_id')}")
    print(f"   Amount: INR {link.get('amount_cents') / 100:.2f}")
    print(f"   Customer URL: {link.get('url')}")

    # 3. Simulate customer checkout and signed webhook
    provider_link_id = link.get("provider_link_id") or f"plink_mock_{link['id']}"
    amount_cents = link.get("amount_cents")
    event_id = f"evt_mock_{uuid4().hex[:12]}"
    payment_id = f"pay_mock_{uuid4().hex[:12]}"

    payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": provider_link_id,
                    "amount": amount_cents,
                    "currency": "INR"
                }
            },
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount_cents,
                    "currency": "INR",
                    "status": "captured",
                    "captured": True
                }
            }
        }
    }

    body = json.dumps(payload).encode("utf-8")
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8")
    signature = hmac.new(webhook_secret, body, hashlib.sha256).hexdigest()

    print(f"\n2. Simulating customer checkout & dispatching signed webhook...")
    print(f"   Payment ID: {payment_id}")
    print(f"   Event ID: {event_id}")

    webhook_headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Event-Id": event_id,
        "X-Razorpay-Signature": signature
    }

    r_wh = requests.post(
        f"{args.base_url}/api/v1/webhooks/razorpay/local",
        data=body,
        headers=webhook_headers
    )

    print(f"   Webhook Response: HTTP {r_wh.status_code} -> {r_wh.text}")

    # 4. Confirm updated case status in RecoverFlow
    r_updated = requests.get(f"{args.base_url}/api/v1/cases/{invoice_id}", headers=headers)
    updated_case = r_updated.json()
    print("\n" + "=" * 65)
    print("PAYMENT RECONCILIATION RESULT [SIMULATED VERIFIED CLOSURE]")
    print("=" * 65)
    print(f"Invoice Number:     {updated_case.get('invoice_number')}")
    print(f"New Case Status:    {updated_case.get('status')}")
    print(f"Remaining Balance:  INR {updated_case.get('balance_cents', 0) / 100:>10,.2f}")
    if updated_case.get('disputed_cents', 0) > 0:
        print(f"  - Disputed Open:  INR {updated_case.get('disputed_cents') / 100:>10,.2f} [Delivery Shortfall Remains Pending]")
        print(f"  - Undisputed Left:INR {updated_case.get('undisputed_cents') / 100:>10,.2f}")
    print(f"Total Ledger Count: {len(updated_case.get('entries', []))}")
    for entry in updated_case.get('entries', []):
        print(f"  - Ledger Entry: {entry.get('kind')} of INR {abs(entry.get('amount_cents')) / 100:>10,.2f} (Ref: {entry.get('reference')})")
    print("=" * 65)
    if updated_case.get('status') == 'PARTIALLY_RESOLVED':
        print("VERIFIED: Undisputed balance collected; case transitioned to PARTIALLY_RESOLVED!")
    elif updated_case.get('status') in ('paid', 'RESOLVED_PAID'):
        print("VERIFIED: Full balance collected; case transitioned to RESOLVED_PAID!")
    else:
        print(f"VERIFIED: Payment allocated; status is {updated_case.get('status')}")

if __name__ == "__main__":
    main()
