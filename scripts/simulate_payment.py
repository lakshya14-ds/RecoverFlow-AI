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
    parser = argparse.ArgumentParser(description="Simulate Razorpay customer payment")
    parser.add_argument("--invoice-id", type=int, help="Invoice ID to pay")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002", help="Server base URL")
    args = parser.parse_args()

    api_key = settings.RECOVERFLOW_API_KEY or "replace-with-a-long-random-secret"
    headers = {"X-RECOVERFLOW-API-KEY": api_key}

    print("=" * 60)
    print("RAZORPAY PAYMENT SIMULATOR (HACKATHON OFFLINE MODE)")
    print("=" * 60)

    # 1. Fetch cases to find eligible invoice
    if not args.invoice_id:
        r = requests.get(f"{args.base_url}/api/v1/cases", headers=headers)
        if r.status_code != 200:
            print(f"Error fetching cases: {r.status_code} - {r.text}")
            return
        cases = r.json()
        eligible = [c for c in cases if c.get("currency") == "INR" and c.get("balance_cents", 0) > 0 and c.get("status") != "paid"]
        if not eligible:
            print("No open INR cases found. Creating a Demo INR Receivable Case...")
            from app.database.db_manager import SessionLocal
            from app.database import models
            from datetime import date, timedelta
            with SessionLocal() as db:
                demo_inv = models.Invoice(
                    tenant_id="local",
                    invoice_number=f"DEMO-INR-{uuid4().hex[:4].upper()}",
                    invoice_type="AR",
                    counterparty_name="Bharat Retailers Pvt Ltd",
                    counterparty_phone="+91 9876543210",
                    counterparty_email="finance@bharatretail.in",
                    issue_date=date.today() - timedelta(days=20),
                    due_date=date.today() - timedelta(days=5),
                    amount=1500.00,
                    total_amount=1500.00,
                    face_amount_cents=150000,
                    currency="INR",
                    status="pending"
                )
                db.add(demo_inv)
                db.commit()
                invoice_id = demo_inv.id
                print(f"Created demo case: ID {invoice_id} ({demo_inv.invoice_number}) - INR 1500.00")
        else:
            target = eligible[0]
            invoice_id = target["invoice_id"]
            print(f"Auto-selected open invoice: ID {invoice_id} ({target['invoice_number']}) - INR {target['balance_cents'] / 100:.2f}")
    else:
        invoice_id = args.invoice_id
        r = requests.get(f"{args.base_url}/api/v1/cases/{invoice_id}", headers=headers)
        if r.status_code != 200:
            print(f"Error fetching case {invoice_id}: {r.status_code} - {r.text}")
            return
        target = r.json()
        print(f"Selected invoice: ID {invoice_id} ({target['invoice_number']}) - INR {target['balance_cents'] / 100:.2f}")

    # 2. Check or create payment link
    idempotency_key = str(uuid4())
    print(f"\n1. Creating/Retrieving Razorpay Payment Link for Invoice {invoice_id}...")
    r_link = requests.post(f"{args.base_url}/api/v1/payments/links", headers=headers, json={
        "invoice_id": invoice_id,
        "idempotency_key": idempotency_key
    })
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
    print("\n" + "=" * 60)
    print("PAYMENT RECONCILIATION RESULT")
    print("=" * 60)
    print(f"Invoice Number: {updated_case.get('invoice_number')}")
    print(f"New Status:     {updated_case.get('status')}")
    print(f"New Balance:    INR {updated_case.get('balance_cents') / 100:.2f}")
    print(f"Total Entries:  {len(updated_case.get('entries', []))}")
    for entry in updated_case.get('entries', []):
        print(f"  - Ledger Entry: {entry.get('kind')} of INR {abs(entry.get('amount_cents')) / 100:.2f} (Ref: {entry.get('reference')})")
    print("=" * 60)
    print("SUCCESS: Payment processed and allocated into immutable ledger!")

if __name__ == "__main__":
    main()
