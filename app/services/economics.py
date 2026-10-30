"""Unit-economics report: measured usage x priced assumptions.

F3. The report keeps three sections strictly apart:

- measured: counts read from this tenant's rows (model calls, messages,
  posted payments, stored bytes, active cases). No prices involved.
- assumptions: unit prices from tenant settings (or global/config
  defaults). Every value carries its source so a default zero is never
  mistaken for a measured zero.
- computed: measured x assumptions, plus per-case figures and a
  variable-cost sensitivity band.

Model calls cover supervisor specialist tasks only; intake/vision
extraction calls are not instrumented yet (see pending). Willingness to
pay needs F2 interviews and is always reported pending.
"""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.config import settings
from app.database import models
from app.services.tenant_config import GLOBAL_SETTING_FALLBACK

COST_DEFAULTS = {
    "cost_per_1k_model_calls": "0",
    "cost_per_outbound_msg": "0",
    "cost_payment_fee_pct": "0",
    "cost_payment_fee_flat": "0",
    "cost_per_gb_month_storage": "0",
    "cost_monthly_infra": "0",
    "cost_monthly_support": "0",
}
VARIABLE_LINES = ("model", "messaging", "payment_fees", "storage")
GB = Decimal(1024 ** 3)


def _naive_utc():
    return datetime.utcnow()


def _assumption(db, tenant_id, key):
    """(Decimal value, source) with source in tenant_setting/global/default."""
    default = COST_DEFAULTS[key]
    row = db.query(models.TenantSetting).filter_by(
        tenant_id=tenant_id, key=key).first()
    if row is not None:
        return _decimal(row.value, default), "tenant_setting"
    if tenant_id == "local":
        env_value = getattr(settings, GLOBAL_SETTING_FALLBACK[key], None)
        if env_value not in (None, ""):
            return _decimal(env_value, default), "global_setting"
    return Decimal(default), "default"


def _decimal(value, default):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _cents(value):
    return (value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def collect_report(db, tenant_id, period_days=30):
    """Assemble measured usage, assumptions, computed costs, sensitivity."""
    if period_days not in range(1, 366):
        raise ValueError("period_days must be 1..365")
    since = _naive_utc() - timedelta(days=period_days)

    tasks = db.query(models.SupervisorTask).filter(
        models.SupervisorTask.tenant_id == tenant_id,
        models.SupervisorTask.created_at >= since).all()
    model_calls = sum(t.model_calls or 0 for t in tasks)
    latencies = [t.elapsed_ms for t in tasks if t.elapsed_ms is not None]
    cases_with_tasks = len({t.invoice_id for t in tasks if t.invoice_id})

    outbound = db.query(models.OutboundMessage).filter(
        models.OutboundMessage.tenant_id == tenant_id,
        models.OutboundMessage.created_at >= since).all()
    by_status = {}
    for row in outbound:
        by_status[row.status] = by_status.get(row.status, 0) + 1

    payments = db.query(models.ReceivableEntry).filter(
        models.ReceivableEntry.tenant_id == tenant_id,
        models.ReceivableEntry.kind == "payment",
        models.ReceivableEntry.created_at >= since).all()
    volume_by_currency = {}
    for row in payments:
        bucket = volume_by_currency.setdefault(row.currency, 0)
        # Receipts reduce receivables: the ledger stores payments as negative.
        # Report gross collected volume positively; reversals stay separate.
        volume_by_currency[row.currency] = bucket - (row.amount_cents or 0)
    reversals = db.query(models.ReceivableEntry).filter(
        models.ReceivableEntry.tenant_id == tenant_id,
        models.ReceivableEntry.kind == "reversal",
        models.ReceivableEntry.created_at >= since).count()

    stored_bytes = sum(
        r.size_bytes or 0 for r in db.query(models.StoredDocument).filter(
            models.StoredDocument.tenant_id == tenant_id,
            models.StoredDocument.deleted_at.is_(None)).all())
    intake_bytes = sum(
        r.size_bytes or 0 for r in db.query(models.IntakeUpload).filter(
            models.IntakeUpload.tenant_id == tenant_id).all())

    row = db.query(models.TenantSetting).filter_by(
        tenant_id=tenant_id, key="cost_currency").first()
    currency = row.value if row else (
        getattr(settings, "COST_CURRENCY", None) or "INR")

    assumptions = {}
    prices = {}
    for key in COST_DEFAULTS:
        value, source = _assumption(db, tenant_id, key)
        assumptions[key] = {"value": format(value, "f"), "source": source}
        prices[key] = value

    home_volume = Decimal(volume_by_currency.get(currency, 0)) / 100
    home_count = sum(1 for row in payments if row.currency == currency)
    lines = {
        "model": Decimal(model_calls) * prices["cost_per_1k_model_calls"] / 1000,
        "messaging": Decimal(len(outbound)) * prices["cost_per_outbound_msg"],
        # Gateway fees apply to reporting-currency volume only; other
        # currencies are listed under pending, never converted silently.
        "payment_fees": (home_volume * prices["cost_payment_fee_pct"] / 100
                         + Decimal(home_count) * prices["cost_payment_fee_flat"]),
        "storage": (Decimal(stored_bytes + intake_bytes) / GB
                    * prices["cost_per_gb_month_storage"]
                    * Decimal(period_days) / 30),
        "infra": prices["cost_monthly_infra"] * Decimal(period_days) / 30,
        "support": prices["cost_monthly_support"] * Decimal(period_days) / 30,
    }
    lines = {name: _cents(amount) for name, amount in lines.items()}
    total = _cents(sum(lines.values()))
    per_case = (_cents(total / cases_with_tasks)
                if cases_with_tasks else None)

    variable = _cents(sum(lines[name] for name in VARIABLE_LINES))
    fixed = _cents(total - variable)
    sensitivity = {}
    for label, factor in (("volume_up_20pct", Decimal("1.2")),
                          ("volume_down_20pct", Decimal("0.8"))):
        sensitivity[label] = {
            "total": format(_cents(variable * factor + fixed), "f"),
            "note": "scales model/messaging/fees/storage; infra+support fixed",
        }

    pending = ["willingness_to_pay (needs F2 pilot interviews)"]
    if model_calls and prices["cost_per_1k_model_calls"] == 0:
        pending.append("model unit price (set cost_per_1k_model_calls from the provider invoice)")
    if outbound and prices["cost_per_outbound_msg"] == 0:
        pending.append("message unit price (set cost_per_outbound_msg from the provider tariff)")
    if payments and prices["cost_payment_fee_pct"] == 0 and prices["cost_payment_fee_flat"] == 0:
        pending.append("gateway fees (set cost_payment_fee_pct/flat from the gateway statement)")
    pending.append("intake/vision extraction model calls are not instrumented yet; "
                   "model_calls covers supervisor tasks only")
    other_currencies = sorted(c for c in volume_by_currency if c != currency)
    if other_currencies:
        pending.append("payment volume in " + ", ".join(other_currencies)
                       + " is excluded from gateway-fee math (reporting currency "
                       + currency + ")")

    return {
        "tenant_id": tenant_id,
        "period_days": period_days,
        "currency": currency,
        "measured": {
            "model_calls": model_calls,
            "model_tasks": len(tasks),
            "model_elapsed_ms_total": sum(latencies),
            "outbound_messages": {"total": len(outbound), "by_status": by_status},
            "posted_payments": {"count": len(payments),
                                "volume_cents_by_currency": volume_by_currency,
                                "reversals": reversals},
            "storage_bytes": {"documents": stored_bytes, "intake": intake_bytes},
            "cases_with_tasks": cases_with_tasks,
        },
        "assumptions": assumptions,
        "computed": {
            "lines": {name: format(amount, "f") for name, amount in lines.items()},
            "total": format(total, "f"),
            "per_case": format(per_case, "f") if per_case is not None else None,
            "per_business": format(total, "f"),
        },
        "sensitivity": sensitivity,
        "pending": pending,
    }
