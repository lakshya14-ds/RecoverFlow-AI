"""Customer communication policy: quiet hours, templates, consent, delivery.

All times are Asia/Kolkata. In-window replies to a customer message send
(sandbox unless the channel is enabled); template sends on triaged threads
need an approved template, channel consent, and open hours — otherwise they
hold. Cold-proactive (threadless) sends are not built yet.
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.database import models

IST = ZoneInfo("Asia/Kolkata")
LANGUAGES = ("en", "hi", "hinglish")
CHANNELS = ("whatsapp", "email")
BASES = ("explicit", "implicit", "contract")


class CommsBlocked(ValueError):
    """A send that policy refuses. Message is safe to show."""


def now_ist():
    return datetime.now(timezone.utc).astimezone(IST)


def in_quiet_hours(start_hhmm, end_hhmm, at=None):
    """True when `at` (IST) falls inside [start, end), wrapping midnight."""
    moment = (at or now_ist()).strftime("%H:%M")
    if start_hhmm <= end_hhmm:
        return start_hhmm <= moment < end_hhmm
    return moment >= start_hhmm or moment < end_hhmm


def quiet_window(db, tenant_id):
    from app.services import tenant_config
    start = tenant_config.get_setting(
        db, tenant_id, "comms_quiet_start", default="21:00") or "21:00"
    end = tenant_config.get_setting(
        db, tenant_id, "comms_quiet_end", default="09:00") or "09:00"
    return start, end


def toggle_on(db, tenant_id, key):
    """Per-tenant channel toggle; accepts stored strings and bool fallback."""
    from app.services import tenant_config
    value = tenant_config.get_setting(db, tenant_id, key, default="false")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() == "true"


def render_template(body, variables):
    """Substitute Meta-style {{1}} vars. Missing or extra vars are errors."""
    wanted = sorted({int(number) for number in re.findall(r"{{(\d+)}}", body or "")})
    given = variables or []
    if wanted != list(range(1, len(given) + 1)):
        raise CommsBlocked(
            f"Template needs exactly {len(wanted)} variable(s), "
            f"got {len(given)}")
    rendered = body
    for position, value in enumerate(given, start=1):
        text = str(value or "").strip()
        if not text:
            raise CommsBlocked(f"Template variable {position} is empty")
        if len(text) > 200:
            raise CommsBlocked(f"Template variable {position} is too long")
        rendered = rendered.replace("{{%d}}" % position, text)
    return rendered


def preference_for(db, tenant_id, invoice_id, channel):
    return db.query(models.CommsPreference).filter_by(
        tenant_id=tenant_id, invoice_id=invoice_id, channel=channel).first()


def check_template_send(db, tenant_id, invoice, channel, template, language,
                        at=None):
    """Gate a template send on a triaged thread. Returns (preference, hold)."""
    if channel not in CHANNELS:
        raise CommsBlocked("Unknown channel")
    if invoice.contact_opt_out:
        raise CommsBlocked("Customer has opted out of contact")
    # Suppression pauses automated contact, not a staff reply on the triaged
    # thread itself, so it does not block here.
    if template.status != "approved":
        raise CommsBlocked("Template is not approved")
    if language not in LANGUAGES:
        raise CommsBlocked("Unknown language")
    if template.language != language:
        raise CommsBlocked("Template language does not match the preference")
    pref = preference_for(db, tenant_id, invoice.id, channel)
    if not pref or not pref.opted_in:
        raise CommsBlocked("No opt-in consent for this channel")
    start, end = quiet_window(db, tenant_id)
    if in_quiet_hours(start, end, at=at):
        moment = at or now_ist()
        release = moment.replace(hour=int(end[:2]), minute=int(end[3:]),
                                 second=0, microsecond=0)
        if release <= moment:
            release += timedelta(days=1)
        return pref, release.astimezone(timezone.utc).replace(tzinfo=None)
    return pref, None


def apply_delivery(db, tenant_id, provider_message_id, status, errors):
    """Record a provider delivery receipt. Returns the row or None."""
    if not provider_message_id:
        return None
    row = db.query(models.OutboundMessage).filter_by(
        tenant_id=tenant_id,
        provider_message_id=provider_message_id).first()
    if not row:
        return None
    now = datetime.now(timezone.utc)
    if status in ("delivered", "read"):
        row.status = "delivered"
        row.delivered_at = now
        row.failure_reason = None
    elif status == "failed":
        row.status = "failed"
        first = (errors or [{}])[0] or {}
        code = first.get("code", "")
        title = first.get("title") or first.get("message") or "Delivery failed"
        row.failure_reason = f"{code} {title}".strip()[:500]
    elif status == "sent" and row.status in ("sending", "queued",
                                             "sandbox_sent"):
        row.status = "sent"
    db.add(models.AuditEvent(tenant_id=tenant_id, actor="meta_whatsapp_webhook",
        action="message_delivery_updated", entity_type="outbound_message",
        entity_id=str(row.id), details=f"{provider_message_id}:{status}"))
    db.flush()
    return row
