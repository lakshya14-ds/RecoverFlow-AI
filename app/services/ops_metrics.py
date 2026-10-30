"""Operational metrics and alerts. Counts, ages, and error categories only:
no counterparty names, phones, invoice numbers, amounts, or message bodies
ever appear here. Model cost is pending a pricing table; calls and latency
are real measurements.
"""
from datetime import datetime, timedelta

from app.config import settings
from app.database import models
from app.services import worker_lease


def _naive_utc():
    return datetime.utcnow()


def _age_seconds(created):
    if not created:
        return None
    if getattr(created, "tzinfo", None) is not None:
        created = created.replace(tzinfo=None)
    return max(0, int((_naive_utc() - created).total_seconds()))


def queue_stats(db, tenant_id):
    """Depth and oldest age per scope and status."""
    stats = {}
    for scope in ("intake", "supervisor"):
        model = worker_lease.leased_model(scope)
        rows = db.query(model).filter_by(tenant_id=tenant_id).all()
        by_status = {}
        for row in rows:
            bucket = by_status.setdefault(
                row.status, {"count": 0, "oldest_age_seconds": 0})
            bucket["count"] += 1
            age = _age_seconds(row.created_at) or 0
            bucket["oldest_age_seconds"] = max(
                bucket["oldest_age_seconds"], age)
        stats[scope] = by_status
    return stats


def provider_stats(db, tenant_id, hours=24):
    """Provider events by provider and status over the trailing window."""
    since = _naive_utc() - timedelta(hours=hours)
    rows = db.query(models.ProviderEvent).filter(
        models.ProviderEvent.tenant_id == tenant_id,
        models.ProviderEvent.created_at >= since).all()
    stats = {}
    for row in rows:
        bucket = stats.setdefault(
            row.provider, {}).setdefault(row.status, 0)
        stats[row.provider][row.status] = bucket + 1
    return stats


def model_stats(db, tenant_id, hours=24):
    """Model calls and specialist latency. Cost is not tracked yet."""
    since = _naive_utc() - timedelta(hours=hours)
    rows = db.query(models.SupervisorTask).filter(
        models.SupervisorTask.tenant_id == tenant_id,
        models.SupervisorTask.created_at >= since).all()
    calls = sum(row.model_calls or 0 for row in rows)
    latencies = [row.elapsed_ms for row in rows
                 if row.elapsed_ms is not None]
    return {"tasks": len(rows), "model_calls": calls,
            "latency_ms": {
                "avg": int(sum(latencies) / len(latencies)) if latencies else 0,
                "max": max(latencies) if latencies else 0},
            "cost": "not_tracked"}


def message_stats(db, tenant_id, hours=24):
    """Outbound delivery outcomes over the trailing window."""
    since = _naive_utc() - timedelta(hours=hours)
    rows = db.query(models.OutboundMessage).filter(
        models.OutboundMessage.tenant_id == tenant_id,
        models.OutboundMessage.created_at >= since).all()
    stats = {}
    for row in rows:
        stats[row.status] = stats.get(row.status, 0) + 1
    return stats


def discrepancy_stats(db, tenant_id):
    """Open money-adjacent queues: provider discrepancies + allocations."""
    discs = db.query(models.PaymentDiscrepancy).filter_by(
        tenant_id=tenant_id, status="open").all()
    by_kind = {}
    for row in discs:
        by_kind[row.kind] = by_kind.get(row.kind, 0) + 1
    proposals = db.query(models.AllocationProposal).filter(
        models.AllocationProposal.tenant_id == tenant_id,
        models.AllocationProposal.status.in_(
            ["proposed", "partially_applied"])).count()
    return {"payment_discrepancies": by_kind,
            "open_allocation_proposals": proposals}


def dead_letters(db, tenant_id):
    """Dead-letter depth per scope."""
    counts = {}
    for scope in ("intake", "supervisor"):
        model = worker_lease.leased_model(scope)
        counts[scope] = db.query(model).filter_by(
            tenant_id=tenant_id, status="dead_letter").count()
    return counts


def collect_metrics(db, tenant_id):
    """One snapshot for the operator dashboard. No customer data."""
    return {"queues": queue_stats(db, tenant_id),
            "provider_events_24h": provider_stats(db, tenant_id),
            "models_24h": model_stats(db, tenant_id),
            "messages_24h": message_stats(db, tenant_id),
            "discrepancies": discrepancy_stats(db, tenant_id),
            "dead_letters": dead_letters(db, tenant_id)}


ALERTS = [
    {"name": "intake_queue_stalled", "severity": "high", "owner": "oncall",
     "first_response": "Check GET /system/jobs?scope=intake for the oldest "
                       "queued row, then the worker process and its logs."},
    {"name": "supervisor_queue_stalled", "severity": "high", "owner": "oncall",
     "first_response": "Check GET /system/jobs?scope=supervisor for the "
                       "oldest queued task, then the worker process."},
    {"name": "dead_letters_present", "severity": "high", "owner": "operator",
     "first_response": "Inspect GET /system/jobs?status=dead_letter, fix the "
                       "cause, then requeue or dismiss each row."},
    {"name": "provider_review_backlog", "severity": "medium",
     "owner": "collections_staff",
     "first_response": "Work the provider review queues (payments, messages) "
                       "oldest first; escalate repeated signature failures."},
    {"name": "model_latency_high", "severity": "medium", "owner": "oncall",
     "first_response": "Check provider status and recent error categories; "
                       "consider lowering model budgets temporarily."},
    {"name": "delivery_failures", "severity": "medium", "owner": "operator",
     "first_response": "Open the failed outbound rows for provider error "
                       "codes; fix numbers/consent, then have staff resend."},
    {"name": "unreconciled_settlements", "severity": "high",
     "owner": "collections_staff",
     "first_response": "Work GET /payments/discrepancies for settlement "
                       "kinds; match the next provider report."},
    {"name": "allocation_backlog", "severity": "medium",
     "owner": "collections_staff",
     "first_response": "Review scored allocation candidates oldest first; "
                       "ambiguous matches stay parked for staff."},
]


def evaluate_alerts(db, tenant_id):
    """Evaluate every alert rule against current state. See docs/runbook.md."""
    metrics = collect_metrics(db, tenant_id)
    stall_seconds = settings.OPS_QUEUE_STALL_MINUTES * 60
    states = {}

    def oldest(scope):
        queued = metrics["queues"].get(scope, {}).get("queued", {})
        return queued.get("oldest_age_seconds", 0)

    states["intake_queue_stalled"] = {
        "firing": oldest("intake") > stall_seconds,
        "detail": {"oldest_queued_age_seconds": oldest("intake")}}
    states["supervisor_queue_stalled"] = {
        "firing": oldest("supervisor") > stall_seconds,
        "detail": {"oldest_queued_age_seconds": oldest("supervisor")}}
    dead = metrics["dead_letters"]
    states["dead_letters_present"] = {
        "firing": sum(dead.values()) > 0, "detail": dead}
    review = sum(provider.get("needs_review", 0)
                 for provider in metrics["provider_events_24h"].values())
    states["provider_review_backlog"] = {
        "firing": review > settings.OPS_PROVIDER_REVIEW_THRESHOLD,
        "detail": {"needs_review_24h": review}}
    avg_latency = metrics["models_24h"]["latency_ms"]["avg"]
    states["model_latency_high"] = {
        "firing": avg_latency > settings.OPS_MODEL_LATENCY_MS,
        "detail": {"avg_latency_ms_24h": avg_latency}}
    failed = metrics["messages_24h"].get("failed", 0)
    states["delivery_failures"] = {
        "firing": failed > 0, "detail": {"failed_24h": failed}}
    settlement = sum(count for kind, count in
                     metrics["discrepancies"]["payment_discrepancies"].items()
                     if kind.startswith("settlement_"))
    states["unreconciled_settlements"] = {
        "firing": settlement > 0, "detail": {"open_settlement_items": settlement}}
    backlog = metrics["discrepancies"]["open_allocation_proposals"]
    states["allocation_backlog"] = {
        "firing": backlog > settings.OPS_ALLOCATION_BACKLOG,
        "detail": {"open_proposals": backlog}}

    return [{**rule, "state": "firing" if states[rule["name"]]["firing"] else "ok",
             "detail": states[rule["name"]]["detail"]} for rule in ALERTS]
