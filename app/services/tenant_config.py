"""Per-business provider credentials (by reference) and non-secret settings.

Credential VALUES are never stored in the database: a TenantSecret row holds a
pointer (`env:NAME` or `file:/abs/path`) that is resolved at use time. Values
must never enter API responses, logs, fixtures, or handoff notes. The `local`
tenant keeps working from the existing global settings as a fallback so the
pilot database needs no reconfiguration.
"""
import os
import re
from pathlib import Path

from app.config import settings
from app.database import models

TENANT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")

SECRET_SPECS = {
    ("razorpay", "webhook_secret"),
    ("razorpay", "key_secret"),
    ("meta_whatsapp", "app_secret"),
    ("meta_whatsapp", "verify_token"),
    ("meta_whatsapp", "access_token"),
    ("shopify", "webhook_secret"),
    ("shopify", "admin_token"),
}

GLOBAL_FALLBACK = {
    ("razorpay", "webhook_secret"): "RAZORPAY_WEBHOOK_SECRET",
    ("razorpay", "key_secret"): "RAZORPAY_KEY_SECRET",
    ("meta_whatsapp", "app_secret"): "META_WHATSAPP_APP_SECRET",
    ("meta_whatsapp", "verify_token"): "META_WHATSAPP_VERIFY_TOKEN",
    ("meta_whatsapp", "access_token"): "META_WHATSAPP_ACCESS_TOKEN",
    ("shopify", "webhook_secret"): "SHOPIFY_WEBHOOK_SECRET",
    ("shopify", "admin_token"): "SHOPIFY_ADMIN_ACCESS_TOKEN",
}


def _validate_afis_path(value):
    path = Path(value)
    if not value or not path.is_file():
        raise ValueError("afis_db_path must be an existing file")
    return str(path)


def _validate_mode(value):
    if str(value).lower() not in ("test", "live"):
        raise ValueError("razorpay_mode must be test or live")
    return str(value).lower()


def _validate_key_id(value):
    if not re.fullmatch(r"rzp_(test|live)_[A-Za-z0-9]+", value or ""):
        raise ValueError("razorpay_key_id must look like rzp_test_... or rzp_live_...")
    return value


def _validate_phone_id(value):
    if not re.fullmatch(r"[0-9]{4,20}", value or ""):
        raise ValueError("meta_whatsapp_phone_number_id must be 4-20 digits")
    return value


def _validate_shop_domain(value):
    domain = (value or "").strip().lower()
    if not (domain.endswith(".myshopify.com") and domain.count(".") == 2):
        raise ValueError("shopify_shop_domain must be a *.myshopify.com store domain")
    return domain


def _validate_hhmm(value, key):
    if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", str(value or "")):
        raise ValueError(f"{key} must be HH:MM in 24h time")
    return str(value)


def _validate_quiet_start(value):
    return _validate_hhmm(value, "comms_quiet_start")


def _validate_quiet_end(value):
    return _validate_hhmm(value, "comms_quiet_end")


def _validate_toggle(value, key):
    normalized = str(value or "").strip().lower()
    if normalized not in ("true", "false"):
        raise ValueError(f"{key} must be true or false")
    return normalized


def _validate_whatsapp_enabled(value):
    return _validate_toggle(value, "whatsapp_enabled")


def _validate_email_enabled(value):
    return _validate_toggle(value, "email_enabled")


def _validate_cost_amount(value, key):
    from decimal import Decimal, InvalidOperation
    try:
        amount = Decimal(str(value or "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{key} must be a non-negative number")
    if amount < 0:
        raise ValueError(f"{key} must be a non-negative number")
    return format(amount, "f")


def _validate_cost_currency(value):
    code = str(value or "").strip().upper()
    import re as _re
    if not _re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError("cost_currency must be a 3-letter code like INR")
    return code


def _validate_cost_pct(value):
    normalized = _validate_cost_amount(value, "cost_payment_fee_pct")
    from decimal import Decimal
    if Decimal(normalized) > 100:
        raise ValueError("cost_payment_fee_pct must be between 0 and 100")
    return normalized


def _validate_cost_per_1k_model_calls(value):
    return _validate_cost_amount(value, "cost_per_1k_model_calls")


def _validate_cost_per_outbound_msg(value):
    return _validate_cost_amount(value, "cost_per_outbound_msg")


def _validate_cost_payment_fee_flat(value):
    return _validate_cost_amount(value, "cost_payment_fee_flat")


def _validate_cost_per_gb_month_storage(value):
    return _validate_cost_amount(value, "cost_per_gb_month_storage")


def _validate_cost_monthly_infra(value):
    return _validate_cost_amount(value, "cost_monthly_infra")


def _validate_cost_monthly_support(value):
    return _validate_cost_amount(value, "cost_monthly_support")


SETTING_SPECS = {
    "afis_db_path": _validate_afis_path,
    "razorpay_mode": _validate_mode,
    "razorpay_key_id": _validate_key_id,
    "meta_whatsapp_phone_number_id": _validate_phone_id,
    "shopify_shop_domain": _validate_shop_domain,
    "comms_quiet_start": _validate_quiet_start,
    "comms_quiet_end": _validate_quiet_end,
    "whatsapp_enabled": _validate_whatsapp_enabled,
    "email_enabled": _validate_email_enabled,
    "cost_currency": _validate_cost_currency,
    "cost_per_1k_model_calls": _validate_cost_per_1k_model_calls,
    "cost_per_outbound_msg": _validate_cost_per_outbound_msg,
    "cost_payment_fee_pct": _validate_cost_pct,
    "cost_payment_fee_flat": _validate_cost_payment_fee_flat,
    "cost_per_gb_month_storage": _validate_cost_per_gb_month_storage,
    "cost_monthly_infra": _validate_cost_monthly_infra,
    "cost_monthly_support": _validate_cost_monthly_support,
}

GLOBAL_SETTING_FALLBACK = {
    "afis_db_path": "AFIS_DB_PATH",
    "razorpay_mode": "RAZORPAY_MODE",
    "razorpay_key_id": "RAZORPAY_KEY_ID",
    "meta_whatsapp_phone_number_id": "META_WHATSAPP_PHONE_NUMBER_ID",
    "shopify_shop_domain": "SHOPIFY_SHOP_DOMAIN",
    "comms_quiet_start": "COMMS_QUIET_START",
    "comms_quiet_end": "COMMS_QUIET_END",
    "whatsapp_enabled": "WHATSAPP_ENABLED",
    "email_enabled": "EMAIL_ENABLED",
    "cost_currency": "COST_CURRENCY",
    "cost_per_1k_model_calls": "COST_PER_1K_MODEL_CALLS",
    "cost_per_outbound_msg": "COST_PER_OUTBOUND_MSG",
    "cost_payment_fee_pct": "COST_PAYMENT_FEE_PCT",
    "cost_payment_fee_flat": "COST_PAYMENT_FEE_FLAT",
    "cost_per_gb_month_storage": "COST_PER_GB_MONTH_STORAGE",
    "cost_monthly_infra": "COST_MONTHLY_INFRA",
    "cost_monthly_support": "COST_MONTHLY_SUPPORT",
}


def check_tenant_slug(tenant_id):
    """Reject malformed tenant path segments before any lookup."""
    if not TENANT_RE.fullmatch(tenant_id or ""):
        raise ValueError("Unknown tenant")
    return tenant_id


def resolve_secret_ref(secret_ref):
    """Resolve `env:NAME` / `file:/path` to its value (or None when absent)."""
    if not secret_ref or ":" not in secret_ref:
        raise ValueError("secret_ref must be env:NAME or file:/abs/path")
    kind, target = secret_ref.split(":", 1)
    if kind == "env":
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target or ""):
            raise ValueError("Invalid env var name in secret_ref")
        return os.environ.get(target) or None
    if kind == "file":
        path = Path(target)
        if not path.is_absolute() or not path.is_file():
            return None
        data = path.read_bytes()
        if len(data) > 4096:
            raise ValueError("Secret file is too large")
        return data.decode("utf-8").strip() or None
    raise ValueError("secret_ref must be env:NAME or file:/abs/path")


def get_secret(db, tenant_id, provider, name):
    """Per-tenant credential value, or the global fallback for `local` only."""
    if (provider, name) not in SECRET_SPECS:
        raise ValueError("Unknown provider secret")
    if tenant_id != "local":
        row = db.query(models.TenantSecret).filter_by(
            tenant_id=tenant_id, provider=provider, name=name).first()
        if not row:
            return None
        return resolve_secret_ref(row.secret_ref)
    row = db.query(models.TenantSecret).filter_by(
        tenant_id="local", provider=provider, name=name).first()
    if row:
        return resolve_secret_ref(row.secret_ref)
    return getattr(settings, GLOBAL_FALLBACK[(provider, name)]) or None


def get_setting(db, tenant_id, key, default=None):
    """Per-tenant setting, or the global fallback for `local` only."""
    if key not in SETTING_SPECS:
        raise ValueError("Unknown tenant setting")
    row = db.query(models.TenantSetting).filter_by(
        tenant_id=tenant_id, key=key).first()
    if row:
        return row.value
    if tenant_id == "local":
        return getattr(settings, GLOBAL_SETTING_FALLBACK[key]) or default
    return default


def afis_path_for_tenant(db, tenant_id):
    """AFIS database path for one business, or None when not configured."""
    path = get_setting(db, tenant_id, "afis_db_path")
    if not path:
        return None
    resolved = Path(path)
    return resolved if resolved.is_file() else None


def set_secret(db, tenant_id, provider, name, secret_ref, label, actor):
    """Store a credential pointer (never the value). Upserts one row."""
    check_tenant_slug(tenant_id)
    if (provider, name) not in SECRET_SPECS:
        raise ValueError("Unknown provider secret")
    resolve_secret_ref(secret_ref)  # validates the format, ignores the value
    row = db.query(models.TenantSecret).filter_by(
        tenant_id=tenant_id, provider=provider, name=name).first()
    if row:
        row.secret_ref = secret_ref
        row.label = (label or "")[:120]
        row.created_by = actor
    else:
        row = models.TenantSecret(tenant_id=tenant_id, provider=provider,
                                  name=name, secret_ref=secret_ref,
                                  label=(label or "")[:120], created_by=actor)
        db.add(row)
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="tenant_secret_configured", entity_type="tenant_secret",
        entity_id=f"{provider}/{name}", details=f"ref={secret_ref.split(':')[0]}"))
    db.flush()
    return row


def delete_secret(db, tenant_id, provider, name, actor):
    row = db.query(models.TenantSecret).filter_by(
        tenant_id=tenant_id, provider=provider, name=name).first()
    if not row:
        return False
    db.delete(row)
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="tenant_secret_removed", entity_type="tenant_secret",
        entity_id=f"{provider}/{name}"))
    db.flush()
    return True


def set_setting(db, tenant_id, key, value, actor):
    """Store a validated non-secret setting. Upserts one row."""
    check_tenant_slug(tenant_id)
    if key not in SETTING_SPECS:
        raise ValueError("Unknown tenant setting")
    normalized = SETTING_SPECS[key](value)
    row = db.query(models.TenantSetting).filter_by(
        tenant_id=tenant_id, key=key).first()
    if row:
        row.value = normalized
        row.updated_by = actor
    else:
        row = models.TenantSetting(tenant_id=tenant_id, key=key,
                                   value=normalized, updated_by=actor)
        db.add(row)
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="tenant_setting_updated", entity_type="tenant_setting",
        entity_id=key))
    db.flush()
    return row


def public_secrets(db, tenant_id):
    """Listable secret metadata: refs and resolvability, never values."""
    rows = db.query(models.TenantSecret).filter_by(
        tenant_id=tenant_id).order_by(models.TenantSecret.provider,
                                      models.TenantSecret.name).all()
    items = []
    for row in rows:
        try:
            configured = bool(resolve_secret_ref(row.secret_ref))
        except ValueError:
            configured = False
        items.append({"provider": row.provider, "name": row.name,
                      "label": row.label, "secret_ref": row.secret_ref,
                      "configured": configured})
    if tenant_id == "local":
        known = {(item["provider"], item["name"]) for item in items}
        for provider, name in sorted(SECRET_SPECS - known):
            items.append({"provider": provider, "name": name, "label": "",
                          "secret_ref": "env:" + GLOBAL_FALLBACK[(provider, name)],
                          "configured": bool(getattr(settings, GLOBAL_FALLBACK[(provider, name)]))})
    return items
