"""Simulate a customer paying a Razorpay Payment Link in hackathon demo mode.

ALL ACTIONS IN THIS SCRIPT ARE SIMULATED IN TEST MODE.
NEVER COMMUNICATES WITH LIVE PAYMENT GATEWAYS OR PROCESSES REAL CURRENCY.
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from uuid import uuid4
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings


def to_cents(amount_val) -> int:
    """Safely convert major units to integer cents using Decimal arithmetic."""
    if amount_val is None:
        return 0
    try:
        d = Decimal(str(amount_val).strip())
        return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError(f"Invalid monetary amount '{amount_val}': {err}") from err


def format_inr(cents: int) -> str:
    """Format integer cents to INR string."""
    d = Decimal(cents) / Decimal("100")
    return f"INR {d:,.2f}"


def main():
    parser = argparse.ArgumentParser(description="Simulate Razorpay customer payment (SIMULATED TEST MODE)")
    parser.add_argument("--invoice-id", type=int, help="Invoice ID to pay")
    parser.add_argument("--amount", type=str, help="Custom payment amount in INR (defaults to undisputed balance)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002", help="Server base URL")
    parser.add_argument("--webhook-secret", type=str, default=None, help="Razorpay webhook secret override")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP request timeout in seconds")
    args = parser.parse_args()

    api_key = settings.RECOVERFLOW_API_KEY or "recoverflow-local-final-qa-2026"
    headers = {"X-RECOVERFLOW-API-KEY": api_key}
    timeout = args.timeout

    print("=" * 70)
    print("RAZORPAY PAYMENT SIMULATOR [SIMULATED TEST ENVIRONMENT - NO REAL MONEY]")
    print("=" * 70)

    # 1. Fetch case details to find eligible invoice
    try:
        if not args.invoice_id:
            r = requests.get(f"{args.base_url}/api/v1/cases", headers=headers, timeout=timeout)
            if r.status_code != 200:
                print(f"[SIMULATED FAILURE] Error fetching cases list: HTTP {r.status_code} - {r.text[:200]}")
                sys.exit(1)
            cases = r.json()
            if not isinstance(cases, list):
                print(f"[SIMULATED FAILURE] Unexpected response format for cases: {type(cases)}")
                sys.exit(1)

            hero_cases = [c for c in cases if c.get("invoice_number") == "INV-2026-HERO" and c.get("status") not in ("paid", "RESOLVED_PAID", "PARTIALLY_RESOLVED")]
            eligible = hero_cases or [c for c in cases if c.get("currency") == "INR" and c.get("balance_cents", 0) > 0 and c.get("status") not in ("paid", "RESOLVED_PAID")]

            if not eligible:
                print("[SIMULATED FAILURE] No open INR cases found with outstanding balance. Run seed scripts first.")
                sys.exit(1)
            target_summary = eligible[0]
            invoice_id = target_summary.get("invoice_id") or target_summary.get("id")
        else:
            invoice_id = args.invoice_id

        r_case = requests.get(f"{args.base_url}/api/v1/cases/{invoice_id}", headers=headers, timeout=timeout)
        if r_case.status_code != 200:
            print(f"[SIMULATED FAILURE] Error fetching case {invoice_id}: HTTP {r_case.status_code} - {r_case.text[:200]}")
            sys.exit(1)
        target = r_case.json()
    except requests.RequestException as err:
        print(f"[SIMULATED FAILURE] Connection error contacting server at {args.base_url}: {err}")
        sys.exit(1)

    initial_balance_cents = int(target.get("balance_cents", 0))
    initial_disputed_cents = int(target.get("disputed_cents", 0))
    initial_undisputed_cents = int(target.get("undisputed_cents", 0))
    initial_status = target.get("status")
    initial_entry_ids = {e["id"] for e in target.get("entries", []) if "id" in e}

    if initial_balance_cents <= 0:
        print(f"[SIMULATED FAILURE] Case {invoice_id} has zero or negative outstanding balance ({format_inr(initial_balance_cents)}). Cannot collect.")
        sys.exit(1)

    # Determine simulated payment amount
    if args.amount:
        try:
            pay_amount_cents = to_cents(args.amount)
        except ValueError as err:
            print(f"[SIMULATED FAILURE] {err}")
            sys.exit(1)
    else:
        pay_amount_cents = initial_undisputed_cents if initial_undisputed_cents > 0 else initial_balance_cents

    if pay_amount_cents <= 0:
        print(f"[SIMULATED FAILURE] Determined payment amount is non-positive ({format_inr(pay_amount_cents)}).")
        sys.exit(1)
    if pay_amount_cents > initial_balance_cents:
        print(f"[SIMULATED FAILURE] Payment amount {format_inr(pay_amount_cents)} exceeds outstanding balance {format_inr(initial_balance_cents)}.")
        sys.exit(1)

    print(f"Target Invoice ID:  {invoice_id} ({target.get('invoice_number')})")
    print(f"Customer Name:      {target.get('customer')}")
    print(f"Initial Status:     {initial_status}")
    print(f"Total Outstanding:  {format_inr(initial_balance_cents)}")
    if initial_disputed_cents > 0:
        print(f"  - Disputed Hold:  {format_inr(initial_disputed_cents)} [Frozen under investigation]")
        print(f"  - Undisputed:     {format_inr(initial_undisputed_cents)} [Eligible for recovery]")
    print(f"Payment to Simulate:{format_inr(pay_amount_cents)} [SIMULATED]")

    # 2. Check or create payment link for the target amount
    idempotency_key = str(uuid4())
    print(f"\n[SIMULATED] Step 1: Requesting simulated payment link for {format_inr(pay_amount_cents)}...")
    link_payload = {
        "invoice_id": invoice_id,
        "idempotency_key": idempotency_key,
        "amount_cents": pay_amount_cents,
    }

    try:
        r_link = requests.post(f"{args.base_url}/api/v1/payments/links", headers=headers, json=link_payload, timeout=timeout)
        if r_link.status_code in (200, 201):
            link = r_link.json()
            print(f"   Payment Link created successfully (ID: {link.get('id')})")
        else:
            # Check for existing matching active link
            r_links = requests.get(f"{args.base_url}/api/v1/payments/links", headers=headers, timeout=timeout)
            if r_links.status_code != 200:
                print(f"[SIMULATED FAILURE] Failed to create or query payment links: HTTP {r_link.status_code} - {r_link.text[:200]}")
                sys.exit(1)
            links = r_links.json()
            active = [l for l in links if l.get("invoice_id") == invoice_id
                      and l.get("amount_cents") == pay_amount_cents
                      and l.get("currency") == "INR"
                      and l.get("status") in ("open", "creating")]
            if not active:
                print(f"[SIMULATED FAILURE] Could not create link and no matching active link found: HTTP {r_link.status_code} - {r_link.text[:200]}")
                sys.exit(1)
            link = active[0]
            print(f"   Reusing existing matching active payment link (ID: {link.get('id')})")
    except requests.RequestException as err:
        print(f"[SIMULATED FAILURE] Network error creating payment link: {err}")
        sys.exit(1)

    provider_link_id = link.get("provider_link_id") or f"plink_mock_{link['id']}"
    link_amount_cents = int(link.get("amount_cents", 0))

    if link_amount_cents != pay_amount_cents:
        print(f"[SIMULATED FAILURE] Payment link amount {format_inr(link_amount_cents)} does not match simulation target {format_inr(pay_amount_cents)}.")
        sys.exit(1)

    print(f"   Provider Link ID: {provider_link_id}")
    print(f"   Link URL:         {link.get('url')}")

    # 3. Resolve signing configuration securely
    webhook_secret_str = (
        args.webhook_secret
        or os.environ.get("RAZORPAY_WEBHOOK_SECRET")
        or settings.RAZORPAY_WEBHOOK_SECRET
    )
    if not webhook_secret_str:
        print("\n[SIMULATED FAILURE] Razorpay webhook secret is not configured.")
        print("Set RAZORPAY_WEBHOOK_SECRET in environment or pass --webhook-secret.")
        print("To check configuration on server, verify .env setting RAZORPAY_WEBHOOK_SECRET.")
        sys.exit(2)

    # 4. Simulate customer checkout and dispatch signed webhook
    event_id = f"evt_mock_{uuid4().hex[:12]}"
    payment_id = f"pay_mock_{uuid4().hex[:12]}"

    payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": provider_link_id,
                    "amount": pay_amount_cents,
                    "currency": "INR"
                }
            },
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": pay_amount_cents,
                    "currency": "INR",
                    "status": "captured",
                    "captured": True
                }
            }
        }
    }

    body = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    webhook_secret_bytes = webhook_secret_str.encode("utf-8")
    signature = hmac.new(webhook_secret_bytes, body, hashlib.sha256).hexdigest()

    print(f"\n[SIMULATED] Step 2: Simulating customer checkout & dispatching signed webhook...")
    print(f"   Payment ID:       {payment_id}")
    print(f"   Event ID:         {event_id}")

    webhook_headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Event-Id": event_id,
        "X-Razorpay-Signature": signature
    }

    try:
        r_wh = requests.post(
            f"{args.base_url}/api/v1/webhooks/razorpay/local",
            data=body,
            headers=webhook_headers,
            timeout=timeout
        )
    except requests.RequestException as err:
        print(f"[SIMULATED FAILURE] Network error posting webhook to {args.base_url}: {err}")
        sys.exit(3)

    if r_wh.status_code != 200:
        print(f"\n[SIMULATED FAILURE] Webhook dispatch rejected by server: HTTP {r_wh.status_code}")
        print(f"   Response detail: {r_wh.text[:300]}")
        if r_wh.status_code == 401:
            print("   Diagnostic: Webhook signature validation failed.")
            print("   Verify that the webhook secret used by this simulator matches the server's RAZORPAY_WEBHOOK_SECRET.")
        sys.exit(3)

    wh_json = r_wh.json()
    print(f"   Webhook accepted: HTTP 200 (Status: {wh_json.get('status')})")

    # 5. Authoritative settlement verification against ledger
    print(f"\n[SIMULATED] Step 3: Verifying ledger entries and updated balances...")
    updated_case = None
    expected_new_balance = initial_balance_cents - pay_amount_cents

    # Bounded polling for asynchronous or synchronous settlement confirmation
    for attempt in range(1, 6):
        try:
            r_check = requests.get(f"{args.base_url}/api/v1/cases/{invoice_id}", headers=headers, timeout=timeout)
            if r_check.status_code == 200:
                candidate = r_check.json()
                new_entries = [
                    e for e in candidate.get("entries", [])
                    if e.get("id") not in initial_entry_ids and e.get("reference") == payment_id
                ]
                if new_entries:
                    updated_case = candidate
                    break
        except requests.RequestException:
            pass
        time.sleep(0.5)

    if not updated_case:
        print(f"[SIMULATED FAILURE] Settlement verification timed out: no new ledger entry found for payment {payment_id}.")
        sys.exit(4)

    updated_entries = updated_case.get("entries", [])
    matching_new_entries = [
        e for e in updated_entries
        if e.get("id") not in initial_entry_ids and e.get("reference") == payment_id
    ]

    if len(matching_new_entries) != 1:
        print(f"[SIMULATED FAILURE] Expected exactly 1 new ledger entry for {payment_id}, found {len(matching_new_entries)}.")
        sys.exit(4)

    posted_entry = matching_new_entries[0]
    posted_cents = abs(int(posted_entry.get("amount_cents", 0)))
    if posted_cents != pay_amount_cents:
        print(f"[SIMULATED FAILURE] Posted ledger amount {format_inr(posted_cents)} != expected simulated amount {format_inr(pay_amount_cents)}.")
        sys.exit(4)

    final_balance_cents = int(updated_case.get("balance_cents", 0))
    if final_balance_cents != expected_new_balance:
        print(f"[SIMULATED FAILURE] Final balance {format_inr(final_balance_cents)} != expected balance {format_inr(expected_new_balance)}.")
        sys.exit(4)

    final_disputed_cents = int(updated_case.get("disputed_cents", 0))
    if initial_disputed_cents > 0 and final_disputed_cents != initial_disputed_cents:
        print(f"[SIMULATED FAILURE] Disputed amount altered unexpectedly from {format_inr(initial_disputed_cents)} to {format_inr(final_disputed_cents)}.")
        sys.exit(4)

    final_status = updated_case.get("status")
    if expected_new_balance == 0 and final_status not in ("paid", "RESOLVED_PAID"):
        print(f"[SIMULATED FAILURE] Zero balance invoice status is {final_status}, expected paid or RESOLVED_PAID.")
        sys.exit(4)
    if expected_new_balance > 0 and initial_disputed_cents > 0 and final_status != "PARTIALLY_RESOLVED":
        print(f"[SIMULATED FAILURE] Case status is {final_status}, expected PARTIALLY_RESOLVED after undisputed payment.")
        sys.exit(4)

    print("\n" + "=" * 70)
    print("SIMULATED PAYMENT VERIFIED AND SETTLED")
    print("=" * 70)
    print(f"Invoice Number:     {updated_case.get('invoice_number')}")
    print(f"Settled Amount:     {format_inr(pay_amount_cents)} [SIMULATED]")
    print(f"Ledger Entry ID:    {posted_entry.get('id')} (Ref: {posted_entry.get('reference')})")
    print(f"Prior Balance:      {format_inr(initial_balance_cents)}")
    print(f"New Balance:        {format_inr(final_balance_cents)}")
    if final_disputed_cents > 0:
        print(f"Disputed Remaining: {format_inr(final_disputed_cents)} [Remains under investigation]")
    print(f"New Case Status:    {final_status}")
    print("=" * 70)
    sys.exit(0)


if __name__ == "__main__":
    main()
