"""Read-only Shopify credit-term import and targeted webhook resync."""
import base64
import hashlib
import hmac
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import models
from app.services.receivables import balance_cents, cents

ORDER_FIELDS = """id name createdAt cancelledAt email phone
  customer { displayName email phone }
  paymentTerms { paymentSchedules(first: 10) {
    nodes { id dueAt balanceDue { amount currencyCode } }
  } }"""
PAGE_QUERY = f"""query RecoverFlowOrders($after: String) {{
  orders(first: 50, after: $after, sortKey: CREATED_AT, reverse: true) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{ {ORDER_FIELDS} }}
  }}
}}"""
ORDER_QUERY = f"""query RecoverFlowOrder($id: ID!) {{
  order(id: $id) {{ {ORDER_FIELDS} }}
}}"""


def configured() -> bool:
    domain = settings.SHOPIFY_SHOP_DOMAIN.strip().lower()
    return bool(domain.endswith(".myshopify.com") and domain.count(".") == 2 and
                settings.SHOPIFY_ADMIN_ACCESS_TOKEN)


def verify_signature(body: bytes, signature: str) -> bool:
    if not settings.SHOPIFY_WEBHOOK_SECRET or not signature:
        return False
    expected = base64.b64encode(hmac.new(settings.SHOPIFY_WEBHOOK_SECRET.encode(), body,
                                          hashlib.sha256).digest()).decode()
    return hmac.compare_digest(signature, expected)


def graphql(query: str, variables: dict) -> dict:
    if not configured():
        raise RuntimeError("Shopify store and Admin API token are not configured")
    url = f"https://{settings.SHOPIFY_SHOP_DOMAIN.lower()}/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
    with httpx.Client(timeout=20) as client:
        response = client.post(url, headers={"X-Shopify-Access-Token": settings.SHOPIFY_ADMIN_ACCESS_TOKEN},
                               json={"query": query, "variables": variables})
        response.raise_for_status()
        data = response.json()
    if data.get("errors") or not data.get("data"):
        raise RuntimeError("Shopify rejected the order query; check scopes and API version")
    return data["data"]


def fetch_page(cursor: str | None) -> dict:
    return graphql(PAGE_QUERY, {"after": cursor})["orders"]


def fetch_order(gid: str) -> dict | None:
    return graphql(ORDER_QUERY, {"id": gid})["order"]


def import_record(db: Session, tenant_id: str, order: dict, counts: dict) -> None:
    gid = order["id"]
    if order.get("cancelledAt"):
        for invoice in db.query(models.Invoice).filter_by(
                tenant_id=tenant_id, source_system="shopify", source_order_id=gid).all():
            invoice.contact_suppressed = True
            invoice.requires_human_review = True
            counts["review"] += 1
        return
    terms = order.get("paymentTerms") or {}
    schedules = (terms.get("paymentSchedules") or {}).get("nodes") or []
    for schedule in schedules:
        due_at = schedule.get("dueAt")
        money = schedule.get("balanceDue") or {}
        external_id = schedule.get("id")
        if not due_at or not external_id or money.get("currencyCode") != "INR":
            counts["skipped"] += 1
            continue
        existing = db.query(models.Invoice).filter_by(
            tenant_id=tenant_id, source_system="shopify", source_record_id=external_id).first()
        try:
            raw_amount = Decimal(str(money["amount"]))
            if raw_amount < 0:
                raise ValueError("Negative schedule balance")
            amount = cents(raw_amount) if raw_amount > 0 else 0
            due = date.fromisoformat(due_at[:10])
            issued = date.fromisoformat(order["createdAt"][:10])
        except (ValueError, KeyError, TypeError, InvalidOperation):
            counts["skipped"] += 1
            continue
        if existing:
            existing.source_order_id = gid
            if (existing.currency != "INR" or existing.due_date != due or
                    balance_cents(db, existing) != amount):
                existing.requires_human_review = True
                existing.contact_suppressed = True
                counts["review"] += 1
            else:
                counts["unchanged"] += 1
            continue
        if amount == 0:
            counts["skipped"] += 1
            continue
        customer = order.get("customer") or {}
        db.add(models.Invoice(
            tenant_id=tenant_id, invoice_number=order["name"], invoice_type="AR",
            counterparty_name=customer.get("displayName") or order["name"],
            counterparty_email=customer.get("email") or order.get("email"),
            counterparty_phone=customer.get("phone") or order.get("phone"),
            issue_date=issued, due_date=due, amount=amount / 100,
            total_amount=amount / 100, face_amount_cents=amount,
            currency="INR", status="pending", source="retail_sync",
            source_system="shopify", source_record_id=external_id,
            source_order_id=gid))
        counts["imported"] += 1


def import_orders(db: Session, tenant_id: str, *, max_pages: int = 10) -> dict:
    """Import eligible schedules; mismatched balances require review."""
    if tenant_id != "local":
        raise ValueError("Shopify is only configured for the local pilot tenant")
    counts = {"imported": 0, "unchanged": 0, "review": 0, "skipped": 0}
    connection = db.query(models.IntegrationConnection).filter_by(
        tenant_id=tenant_id, kind="retail").first()
    if not connection:
        connection = models.IntegrationConnection(tenant_id=tenant_id, kind="retail",
                                                  provider="shopify", status="configured")
        db.add(connection)
    cursor = connection.cursor
    for _ in range(max_pages):
        page = fetch_page(cursor)
        for order in page["nodes"]:
            import_record(db, tenant_id, order, counts)
        db.flush()
        if not page["pageInfo"]["hasNextPage"]:
            cursor = None
            break
        cursor = page["pageInfo"]["endCursor"]
    else:
        counts["more_pages"] = True
    connection.cursor = cursor
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_error = None
    connection.status = "active"
    db.add(models.AuditEvent(tenant_id=tenant_id, actor="shopify_sync",
                             action="shopify_sync", entity_type="integration",
                             entity_id="shopify", details=str(counts)))
    db.commit()
    return counts


def process_queued_events(db: Session, tenant_id: str = "local") -> int:
    """Fetch affected orders by ID instead of trusting webhook financial fields."""
    events = db.query(models.ProviderEvent).filter_by(
        tenant_id=tenant_id, kind="retail", provider="shopify", status="queued").limit(10).all()
    processed = 0
    for event in events:
        order = fetch_order(event.resource_id)
        if not order:
            event.status = "needs_review"
            event.error = "Shopify order was not found"
        else:
            counts = {"imported": 0, "unchanged": 0, "review": 0, "skipped": 0}
            import_record(db, tenant_id, order, counts)
            event.status = "needs_review" if counts["review"] else "processed"
            event.error = "Shopify balance changed; review the case" if counts["review"] else None
        event.processed_at = datetime.now(timezone.utc)
        db.commit()
        processed += 1
    return processed
