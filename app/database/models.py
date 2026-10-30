"""
RecoverFlow - Receivables and Collections
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Text, Boolean, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.db_manager import Base
from app.database.money import Money

class Invoice(Base):
    """
    Represents an Invoice (Accounts Payable or Receivable).
    Stores extracted OCR data, metadata, and validation flags.
    """
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    invoice_number = Column(String, nullable=False)
    invoice_type = Column(String, nullable=False) # 'AP' or 'AR'
    counterparty_name = Column(String, nullable=False, index=True)
    counterparty_email = Column(String)
    counterparty_phone = Column(String)
    counterparty_tax_id = Column(String)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    cgst_cents = Column(Integer, default=0)
    sgst_cents = Column(Integer, default=0)
    igst_cents = Column(Integer, default=0)
    freight_cents = Column(Integer, default=0)
    roundoff_cents = Column(Integer, default=0)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    received_date = Column(Date)
    amount = Column(Money, nullable=False)
    currency = Column(String, default="INR")
    tax_amount = Column(Money, default=0.0)
    total_amount = Column(Money, nullable=False)
    face_amount_cents = Column(Integer)
    description = Column(Text)
    po_number = Column(String)
    status = Column(String, default="pending")
    source = Column(String, default="manual")
    source_system = Column(String)
    source_record_id = Column(String)
    source_order_id = Column(String)
    source_filename = Column(String)
    source_path = Column(String)
    ocr_confidence = Column(Float, default=0.0)
    ocr_raw_text = Column(Text)
    fraud_score = Column(Float, default=0.0, index=True)
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_id = Column(Integer, ForeignKey("invoices.id"))
    requires_human_review = Column(Boolean, default=False)
    human_review_notes = Column(Text)
    contact_suppressed = Column(Boolean, nullable=False, default=False)
    contact_opt_out = Column(Boolean, nullable=False, default=False)
    dispute_open = Column(Boolean, nullable=False, default=False)
    disputed_cents = Column(Integer, nullable=False, default=0)
    investigation_hold = Column(Boolean, nullable=False, default=False)
    investigation_reason = Column(Text)
    investigation_decision_hash = Column(String(64))
    afis_transaction_id = Column(Integer)
    axis_classified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    reconciliations = relationship("Reconciliation", back_populates="invoice")
    dunning_campaigns = relationship("DunningCampaign", back_populates="invoice")
    fraud_alerts = relationship("FraudAlert", back_populates="invoice")

class Reconciliation(Base):
    """
    Represents a reconciliation record matching an Invoice to an AFIS transaction.
    """
    __tablename__ = "reconciliations"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    afis_transaction_id = Column(Integer, nullable=False)
    match_type = Column(String, nullable=False)
    confidence_score = Column(Float, nullable=False)
    matched_amount = Column(Money, nullable=False)
    variance_amount = Column(Money, default=0.0)
    variance_reason = Column(Text)
    match_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    matched_by = Column(String, default="recoverflow_agent")
    status = Column(String, default="pending_review")
    reviewed_by_human = Column(Boolean, default=False)
    human_notes = Column(Text)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="reconciliations")

class ReceivableEntry(Base):
    """Signed, immutable adjustment to an invoice's opening receivable balance."""
    __tablename__ = "receivable_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "source", "reference"), UniqueConstraint("tenant_id", "reversal_of_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    allocation = Column(String, nullable=False, default="legacy")
    disputed_delta_cents = Column(Integer, nullable=False, default=0)
    reversal_of_id = Column(Integer, ForeignKey("receivable_entries.id"))
    currency = Column(String, nullable=False)
    source = Column(String, nullable=False)
    reference = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    note = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class DunningCampaign(Base):
    """
    Represents a dunning (collections) campaign stage for an overdue invoice.
    """
    __tablename__ = "dunning_campaigns"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    campaign_stage = Column(Integer, nullable=False, default=1)
    days_overdue = Column(Integer, nullable=False, default=0)
    tone = Column(String, nullable=False)
    email_subject = Column(String)
    email_body = Column(Text)
    balance_cents_at_draft = Column(Integer)
    email_to = Column(String)
    email_sent = Column(Boolean, default=False)
    email_sent_at = Column(DateTime)
    contacted_at = Column(DateTime)
    contact_channel = Column(String)
    contact_reference = Column(String)
    email_opened = Column(Boolean, default=False)
    email_opened_at = Column(DateTime)
    response_received = Column(Boolean, default=False)
    response_notes = Column(Text)
    next_action_date = Column(Date)
    status = Column(String, default="draft")
    approved_by = Column(String)
    approved_at = Column(DateTime)
    generated_by = Column(String, default="recoverflow_agent")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="dunning_campaigns")

class FraudAlert(Base):
    """
    Records an anomaly or fraud alert generated by the Isolation Forest model.
    """
    __tablename__ = "fraud_alerts"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    alert_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    fraud_score = Column(Float, nullable=False)
    description = Column(Text, nullable=False)
    features_flagged = Column(Text)
    status = Column(String, default="open")
    investigated_by = Column(String)
    resolution_notes = Column(Text)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="fraud_alerts")

class DSOSnapshot(Base):
    """
    Stores daily snapshots of Days Sales Outstanding (DSO) for forecasting.
    """
    __tablename__ = "dso_snapshots"
    __table_args__ = (UniqueConstraint("tenant_id", "snapshot_date"),)
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    snapshot_date = Column(Date, nullable=False)
    dso_days = Column(Float, nullable=False)
    ar_balance = Column(Money, nullable=False)
    revenue_30d = Column(Money, nullable=False)
    overdue_amount = Column(Money, default=0.0)
    overdue_count = Column(Integer, default=0)
    collection_rate = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Counterparty(Base):
    """
    Represents a business entity (Vendor or Customer).
    """
    __tablename__ = "counterparties"
    __table_args__ = (UniqueConstraint("tenant_id", "tax_id"),
                      UniqueConstraint("tenant_id", "gstin"))
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    address = Column(Text)
    tax_id = Column(String)
    gstin = Column(String(15))
    legal_name = Column(String)
    display_name = Column(String)
    billing_address = Column(Text)
    shipping_address = Column(Text)
    status = Column(String, nullable=False, default="active")
    merged_into_id = Column(Integer, ForeignKey("counterparties.id"))
    payment_terms = Column(Integer, default=30)
    credit_limit = Column(Money, default=0.0)
    avg_payment_days = Column(Float, default=0.0)
    on_time_rate = Column(Float, default=1.0)
    total_invoiced = Column(Money, default=0.0)
    total_paid = Column(Money, default=0.0)
    fraud_flag = Column(Integer, default=0)
    risk_score = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class CounterpartyBranch(Base):
    """One business location. Same-state branches may share the HQ GSTIN."""
    __tablename__ = "counterparty_branches"
    __table_args__ = (UniqueConstraint("tenant_id", "counterparty_id", "name"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"),
                             nullable=False, index=True)
    name = Column(String(200), nullable=False)
    gstin = Column(String(15))
    billing_address = Column(Text)
    shipping_address = Column(Text)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CounterpartyExternalId(Base):
    """One foreign-system identity (tally/busy/zoho/shopify/...)."""
    __tablename__ = "counterparty_external_ids"
    __table_args__ = (UniqueConstraint("tenant_id", "system", "external_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"),
                             nullable=False, index=True)
    system = Column(String(40), nullable=False)
    external_id = Column(String(200), nullable=False)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CounterpartyMerge(Base):
    """Immutable record of one staff-confirmed party merge."""
    __tablename__ = "counterparty_merges"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    loser_id = Column(Integer, ForeignKey("counterparties.id"), nullable=False)
    winner_id = Column(Integer, ForeignKey("counterparties.id"), nullable=False)
    moved_invoices = Column(Integer, nullable=False, default=0)
    invoice_ids = Column(Text, nullable=False, default="[]")
    reason = Column(Text, nullable=False)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class InvoiceLineItem(Base):
    """One persisted invoice line. Amounts are taxable; tax splits per line."""
    __tablename__ = "invoice_line_items"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id", "line_no"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False,
                        index=True)
    line_no = Column(Integer, nullable=False)
    sku = Column(String(120), nullable=False, default="")
    description = Column(Text, nullable=False)
    hsn = Column(String(16))
    quantity = Column(Numeric(14, 3))
    unit = Column(String(20), nullable=False, default="")
    unit_price_cents = Column(Integer)
    amount_cents = Column(Integer, nullable=False)
    tax_rate_bps = Column(Integer)
    cgst_cents = Column(Integer, nullable=False, default=0)
    sgst_cents = Column(Integer, nullable=False, default=0)
    igst_cents = Column(Integer, nullable=False, default=0)
    source_upload_id = Column(String)
    status = Column(String, nullable=False, default="alleged")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CreditDebitNote(Base):
    """An alleged or accepted adjustment document. Only posting creates money."""
    __tablename__ = "credit_debit_notes"
    __table_args__ = (UniqueConstraint("tenant_id", "note_type", "number"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False,
                        index=True)
    note_type = Column(String(10), nullable=False)
    number = Column(String(120), nullable=False)
    note_date = Column(Date)
    amount_cents = Column(Integer, nullable=False)
    cgst_cents = Column(Integer, nullable=False, default=0)
    sgst_cents = Column(Integer, nullable=False, default=0)
    igst_cents = Column(Integer, nullable=False, default=0)
    reason = Column(Text, nullable=False)
    source_upload_id = Column(String)
    status = Column(String, nullable=False, default="alleged")
    entry_id = Column(Integer, ForeignKey("receivable_entries.id"))
    created_by = Column(String, nullable=False)
    decided_by = Column(String)
    decided_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SupportingDocument(Base):
    """Challans, freight bills, scheme letters, and other linked evidence."""
    __tablename__ = "supporting_documents"
    __table_args__ = (UniqueConstraint("tenant_id", "source_upload_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False,
                        index=True)
    doc_type = Column(String(40), nullable=False)
    number = Column(String(200))
    doc_date = Column(Date)
    source_upload_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="alleged")
    summary_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class InstallmentSchedule(Base):
    """Accepted cash-payment plan. Nonfinancial: never touches the ledger."""
    __tablename__ = "installment_schedules"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False,
                        index=True)
    promise_id = Column(Integer, ForeignKey("promises_to_pay.id"))
    terms = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="proposed")
    created_by = Column(String, nullable=False)
    approved_by = Column(String)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class InstallmentLeg(Base):
    """One dated slice of a schedule. paid_cents derives from applications."""
    __tablename__ = "installment_legs"
    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey("installment_schedules.id"),
                         nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    paid_cents = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="pending")
    supersedes_id = Column(Integer, ForeignKey("installment_legs.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class InstallmentApplication(Base):
    """One entry-to-leg application. Reversals flag rows, never delete."""
    __tablename__ = "installment_applications"
    __table_args__ = (UniqueConstraint("entry_id", "leg_id"),)
    id = Column(Integer, primary_key=True)
    leg_id = Column(Integer, ForeignKey("installment_legs.id"), nullable=False,
                    index=True)
    entry_id = Column(Integer, ForeignKey("receivable_entries.id"),
                      nullable=False, index=True)
    amount_cents = Column(Integer, nullable=False)
    reversed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RecoverFlowSetting(Base):
    """
    Key-value store for RecoverFlow settings.
    """
    __tablename__ = "apex_settings"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    actor = Column(String, nullable=False, default="system")
    source_path = Column(String, nullable=False)
    invoice_type = Column(String, nullable=False, default="AP")
    attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime)
    status = Column(String, nullable=False, default="queued")
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    error = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class IntakeUpload(Base):
    """Durable upload queue state; file bytes live outside the frontend root."""
    __tablename__ = "intake_uploads"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    sha256 = Column(String(64))
    mime_type = Column(String, nullable=False)
    source_path = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="queued")
    stage = Column(String, nullable=False, default="Uploaded")
    stages_json = Column(Text, nullable=False, default='["Uploaded"]')
    error = Column(Text)
    attempts = Column(Integer, nullable=False, default=0)
    cases_created = Column(Integer, nullable=False, default=0)
    extraction_json = Column(Text)
    claimed_by = Column(String)
    claimed_at = Column(DateTime)
    heartbeat_at = Column(DateTime)
    lease_expires_at = Column(DateTime)
    not_before = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    details = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class CustomerMessage(Base):
    """Staff-recorded customer reply until an inbound provider is configured."""
    __tablename__ = "customer_messages"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    category = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    actor = Column(String, nullable=False)
    is_injection = Column(Boolean, nullable=False, default=False)
    rejection_reason = Column(Text)
    source = Column(String, nullable=False, default="staff")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class IntegrationConnection(Base):
    """Public connection state. Credentials stay in provider-specific secret storage."""
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("tenant_id", "kind"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    status = Column(String, nullable=False, default="disabled")
    external_account_id = Column(String)
    cursor = Column(String)
    last_sync_at = Column(DateTime)
    last_error = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class PaymentLink(Base):
    __tablename__ = "payment_links"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),
                      UniqueConstraint("tenant_id", "provider", "provider_link_id"))
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    provider_link_id = Column(String)
    idempotency_key = Column(String, nullable=False)
    url = Column(Text)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(String, nullable=False, default="open")
    expires_at = Column(DateTime)
    mode = Column(String, nullable=False, default="test")
    last_error = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProviderEvent(Base):
    """Deduplicated verified webhook with processing outcome, excluding raw PII."""
    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "provider", "event_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    event_id = Column(String, nullable=False)
    resource_id = Column(String)
    body_sha256 = Column(String(64), nullable=False)
    mode = Column(String, nullable=False, default="test")
    status = Column(String, nullable=False)
    error = Column(Text)
    resolution_note = Column(Text)
    resolved_by = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime)


class CollectionPolicy(Base):
    """Tenant-controlled schedule for draft creation only; sending still needs approval."""
    __tablename__ = "collection_policies"
    tenant_id = Column(String, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    timezone = Column(String, nullable=False, default="UTC")
    run_hour = Column(Integer, nullable=False, default=9)
    stage1_days = Column(Integer, nullable=False, default=7)
    stage2_days = Column(Integer, nullable=False, default=15)
    stage3_days = Column(Integer, nullable=False, default=30)
    stage4_days = Column(Integer, nullable=False, default=45)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class InboundMessage(Base):
    __tablename__ = "inbound_messages"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "external_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    sender = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True)
    status = Column(String, nullable=False, default="unassigned")
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    inbound_id = Column(Integer, ForeignKey("inbound_messages.id"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    idempotency_key = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    provider_message_id = Column(String)
    recipient = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="sending")
    language = Column(String, nullable=False, default="en")
    template_id = Column(Integer, ForeignKey("message_templates.id"))
    delivered_at = Column(DateTime)
    failure_reason = Column(Text)
    held_until = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentPolicy(Base):
    """Tenant opt-in and hard limits for the controlled agent."""
    __tablename__ = "agent_policies"
    tenant_id = Column(String, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    auto_assess = Column(Boolean, nullable=False, default=False)
    auto_execute_internal = Column(Boolean, nullable=False, default=False)
    max_assessments_per_day = Column(Integer, nullable=False, default=20)
    max_internal_actions_per_day = Column(Integer, nullable=False, default=5)
    max_balance_cents = Column(Integer, nullable=False, default=100000)
    autonomy_mode = Column(String, nullable=False, default="review_all")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class NegotiationSession(Base):
    __tablename__ = "negotiation_sessions"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    mode = Column(String, nullable=False, default="manual")
    status = Column(String, nullable=False, default="active")
    round_count = Column(Integer, nullable=False, default=0)
    max_instalments = Column(Integer, nullable=False, default=3)
    max_extension_days = Column(Integer, nullable=False, default=30)
    min_first_percent = Column(Integer, nullable=False, default=30)
    settlement_discount_allowed = Column(Boolean, nullable=False, default=False)
    max_ai_rounds = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class NegotiationTurn(Base):
    __tablename__ = "negotiation_turns"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("negotiation_sessions.id"), nullable=False, index=True)
    direction = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    context_hash = Column(String(64))
    offer_json = Column(Text)
    body_hash = Column(String(64), nullable=False)
    supersedes_id = Column(Integer, ForeignKey("negotiation_turns.id"))
    approved_by = Column(String)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SandboxOutbox(Base):
    __tablename__ = "sandbox_outbox"
    __table_args__ = (UniqueConstraint("tenant_id", "proposal_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    proposal_id = Column(Integer, ForeignKey("agent_proposals.id"), nullable=False)
    channel = Column(String, nullable=False, default="SIMULATED sandbox")
    body = Column(Text, nullable=False)
    body_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentProposal(Base):
    """One immutable assessment snapshot and its controlled action state."""
    __tablename__ = "agent_proposals"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id", "context_hash"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    inbound_id = Column(Integer, ForeignKey("inbound_messages.id"))
    context_hash = Column(String(64), nullable=False)
    engine = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    action = Column(String, nullable=False)
    draft_text = Column(Text)
    status = Column(String, nullable=False, default="proposed")
    risk_flags = Column(Text, nullable=False, default="[]")
    balance_cents_at_proposal = Column(Integer, nullable=False)
    reviewed_by = Column(String)
    review_note = Column(Text)
    executed_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentCaseNote(Base):
    """The only action the pilot agent can execute on its own."""
    __tablename__ = "agent_case_notes"
    __table_args__ = (UniqueConstraint("tenant_id", "proposal_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    proposal_id = Column(Integer, ForeignKey("agent_proposals.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentExecution(Base):
    """Idempotent record of each bounded internal action."""
    __tablename__ = "agent_executions"
    __table_args__ = (UniqueConstraint("tenant_id", "proposal_id", "action"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    proposal_id = Column(Integer, ForeignKey("agent_proposals.id"), nullable=False)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    result_id = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaseEvidence(Base):
    """Source-linked claim. Trust: alleged < extracted < verified < accepted; rejected ends use.

    Customer statements and model extractions enter as alleged/extracted.
    Staff verify a source (verified) or authorize financial reliance (accepted).
    Old verified=True rows migrate to verified, never accepted."""
    __tablename__ = "case_evidence"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    claim_type = Column(String, nullable=False)  # invoice_total, received_payment, dispute_item, undisputed_balance, purchase_order
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    source_type = Column(String, nullable=False)  # invoice_pdf, bank_receipt, po_document, customer_email, reconciliation_math
    source_reference = Column(String, nullable=False)
    source_snippet = Column(Text)
    amount_cents = Column(Integer)
    verified = Column(Boolean, default=True)
    trust_state = Column(String, nullable=False, default="alleged")
    decided_by = Column(String)
    decided_at = Column(DateTime)
    decision_reason = Column(Text)
    currency = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProposalDraftVersion(Base):
    """Immutable versioned revisions of an agent draft."""
    __tablename__ = "proposal_draft_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "proposal_id", "version_number"),)
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    proposal_id = Column(Integer, ForeignKey("agent_proposals.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1)
    body = Column(Text, nullable=False)
    edited_by = Column(String, nullable=False)
    change_reason = Column(Text)
    version_hash = Column(String(64), nullable=False)
    status = Column(String, nullable=False, default="draft")  # draft, approved, rejected
    approved_by = Column(String)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class User(Base):
    """Database-backed staff and API users with PBKDF2 password hashing."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="editor")  # admin, editor, viewer
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime, nullable=True)


class UserApiKey(Base):
    """Database-backed API keys with SHA-256 hash storage."""
    __tablename__ = "user_api_keys"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    key_prefix = Column(String(16), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    role = Column(String, nullable=False, default="editor")  # admin, editor, viewer
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)


class UserSession(Base):
    """Active user authentication tokens and web sessions."""
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, nullable=False, default=False)


class CaseWorkflow(Base):
    """One durable, versioned lifecycle shared by all processing entry points."""
    __tablename__ = "case_workflows"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    stage = Column(String, nullable=False)
    context_hash = Column(String(64), nullable=False)
    last_event = Column(String, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ItemAlias(Base):
    __tablename__ = "item_aliases"
    __table_args__ = (UniqueConstraint("tenant_id", "alias"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    alias = Column(String(200), nullable=False)
    canonical_sku = Column(String(200), nullable=False)
    approved_by = Column(String, nullable=False)


class SupervisorTask(Base):
    """Durable specialist execution. Outputs are advisory; the ledger moves
    exclusively through existing authorized posting paths."""
    __tablename__ = "supervisor_tasks"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True)
    kind = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    idempotency_key = Column(String, nullable=False)
    input_json = Column(Text, nullable=False, default="{}")
    depends_on_json = Column(Text, nullable=False, default="[]")
    trigger = Column(String, nullable=False, default="manual")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    time_budget_ms = Column(Integer, nullable=False, default=30000)
    model_budget = Column(Integer, nullable=False, default=2)
    model_calls = Column(Integer, nullable=False, default=0)
    case_version = Column(String(64))
    result_json = Column(Text)
    error = Column(Text)
    applied = Column(Boolean, nullable=False, default=False)
    elapsed_ms = Column(Integer)
    claimed_by = Column(String)
    claimed_at = Column(DateTime)
    heartbeat_at = Column(DateTime)
    lease_expires_at = Column(DateTime)
    not_before = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class CompetingExplanation(Base):
    """Conflicting hypotheses for one item+claim. Staff resolve; never auto-picked."""
    __tablename__ = "competing_explanations"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    identity = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    hypotheses_json = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="open")
    resolved_hypothesis = Column(String(100))
    resolved_by = Column(String)
    resolution_reason = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class ClarificationTask(Base):
    """One missing fact blocking a decision, with owner, source, due date, amount."""
    __tablename__ = "clarification_tasks"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    key = Column(String(200), nullable=False)
    title = Column(String(300), nullable=False)
    owner = Column(String(20), nullable=False)
    source = Column(String(300), nullable=False)
    due_date = Column(Date)
    affected_cents = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="open")
    draft_preview = Column(Text)
    created_by = Column(String, nullable=False, default="investigator_agent")
    fulfilled_evidence_id = Column(Integer, ForeignKey("case_evidence.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class UnitRule(Base):
    """Staff-approved unit conversion. No rule, no conversion."""
    __tablename__ = "unit_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "from_unit", "to_unit"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    from_unit = Column(String(50), nullable=False)
    to_unit = Column(String(50), nullable=False)
    factor = Column(String(30), nullable=False)
    approved_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AllocationProposal(Base):
    """Candidate split of one verified transfer across invoices. Staff approve."""
    __tablename__ = "allocation_proposals"
    __table_args__ = (UniqueConstraint("tenant_id", "afis_transaction_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    afis_transaction_id = Column(String(120), nullable=False)
    transfer_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="INR")
    transfer_date = Column(String(20))
    description = Column(Text)
    status = Column(String, nullable=False, default="proposed")
    candidates_json = Column(Text, nullable=False, default="[]")
    created_by = Column(String, nullable=False)
    decided_by = Column(String)
    decision_reason = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AllocationLeg(Base):
    """One invoice leg of a proposal. Posts only through staff approval."""
    __tablename__ = "allocation_legs"
    __table_args__ = (UniqueConstraint("proposal_id", "invoice_id"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    proposal_id = Column(Integer, ForeignKey("allocation_proposals.id"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    allocation = Column(String, nullable=False, default="undisputed_first")
    status = Column(String, nullable=False, default="pending")
    reason = Column(Text)
    entry_id = Column(Integer, ForeignKey("receivable_entries.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PayerAlias(Base):
    """Staff-approved payer-name alias for transfer matching."""
    __tablename__ = "payer_aliases"
    __table_args__ = (UniqueConstraint("tenant_id", "alias"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    alias = Column(String(200), nullable=False)
    counterparty_name = Column(String(200), nullable=False)
    approved_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PromiseToPay(Base):
    """Nonfinancial promise record. Never cash, never closes a case."""
    __tablename__ = "promises_to_pay"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    promised_cents = Column(Integer, nullable=False)
    promised_date = Column(Date)
    source_message_id = Column(Integer, ForeignKey("customer_messages.id"))
    source_text = Column(Text, nullable=False)
    extraction_confidence = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default="alleged")
    confirmed_by = Column(String)
    confirmed_at = Column(DateTime)
    reminders_sent = Column(Integer, nullable=False, default=0)
    last_reminder_at = Column(DateTime)
    broken_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class TenantSecret(Base):
    """Per-business provider credential pointer. The VALUE is never stored here.

    secret_ref is `env:NAME` or `file:/abs/path`; resolution happens at use
    time, and values never enter API responses, logs, fixtures, or handoff."""
    __tablename__ = "tenant_secrets"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "name"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    provider = Column(String(40), nullable=False)
    name = Column(String(60), nullable=False)
    secret_ref = Column(String(300), nullable=False)
    label = Column(String(120), nullable=False, default="")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class TenantSetting(Base):
    """Per-business non-secret configuration. Secrets belong in TenantSecret."""
    __tablename__ = "tenant_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    key = Column(String(80), nullable=False)
    value = Column(Text, nullable=False)
    updated_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class LoginAttempt(Base):
    """Pre-authentication login throttle log. Pruned regularly; never exported."""
    __tablename__ = "login_attempts"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, index=True)
    ip = Column(String(64), nullable=False, index=True)
    success = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class UserRecoveryToken(Base):
    """Single-use admin-issued password recovery. Only the hash is stored."""
    __tablename__ = "user_recovery_tokens"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaseAssignment(Base):
    """Insert-only case ownership history. Latest row is the assignee."""
    __tablename__ = "case_assignments"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    assignee_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignee_email = Column(String(255), nullable=False)
    assigned_by = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class StaffTask(Base):
    """Internal task with assignee, due date, and completion record."""
    __tablename__ = "staff_tasks"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True)
    title = Column(String(200), nullable=False)
    detail = Column(Text, nullable=False, default="")
    assignee_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignee_email = Column(String(255), nullable=False)
    created_by = Column(String, nullable=False)
    status = Column(String(20), nullable=False, default="open")
    due_date = Column(Date)
    completed_by = Column(String)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class StaffNote(Base):
    """Append-only internal case note. Corrections are new notes."""
    __tablename__ = "staff_notes"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    body = Column(Text, nullable=False)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaseEscalation(Base):
    """Raised concern with a deadline. Sweep flips overdue rows to escalated."""
    __tablename__ = "case_escalations"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    deadline = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="open")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_by = Column(String)
    resolved_at = Column(DateTime)


class PortalToken(Base):
    """Single-invoice customer portal access. Only the hash is stored.

    Short-lived, revocable, bound to one tenant + one invoice. The raw token
    is shown once at issue time; lookups use the SHA-256 hash. A token grants
    the fixed portal capability set (view summary, dispute, evidence,
    payment reference) and nothing else."""
    __tablename__ = "portal_tokens"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    prefix = Column(String(12), nullable=False)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)
    revoked_by = Column(String)
    revoke_reason = Column(Text)
    last_used_at = Column(DateTime)
    use_count = Column(Integer, nullable=False, default=0)


class PortalAttempt(Base):
    """Portal authentication + rate-limit log. Pruned regularly; never exported."""
    __tablename__ = "portal_attempts"
    id = Column(Integer, primary_key=True)
    token_id = Column(Integer, ForeignKey("portal_tokens.id"), index=True)
    ip = Column(String(64), nullable=False, index=True)
    success = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class StoredDocument(Base):
    """Private evidence file. Bytes live outside the web root under a random name.

    scan_status: pending (awaiting staff release, the default for portal
    uploads), clean (policy scan passed on a staff-authenticated channel),
    quarantined (staff-flagged; reads blocked). No antivirus engine is wired
    yet; see docs/document-security.md. deleted_at is a soft delete; bytes are
    removed and the row stays for the audit trail."""
    __tablename__ = "stored_documents"
    id = Column(String(32), primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True)
    origin = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    stored_name = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    scan_status = Column(String, nullable=False, default="pending")
    scanned_by = Column(String)
    scanned_at = Column(DateTime)
    scan_detail = Column(Text)
    uploaded_by = Column(String, nullable=False)
    portal_token_id = Column(Integer, ForeignKey("portal_tokens.id"))
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    retention_expires_at = Column(DateTime)
    hold = Column(Boolean, nullable=False, default=False)
    hold_reason = Column(Text)
    deleted_at = Column(DateTime)


class DocumentAccessLog(Base):
    """Every document read or state change. Append-only."""
    __tablename__ = "document_access_log"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    doc_id = Column(String(32), ForeignKey("stored_documents.id"), nullable=False, index=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    ip = Column(String(64))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class ImportRun(Base):
    """One staff-confirmed accounting import batch. Read-only source side.

    payload_json holds the mapped rows; report_json the reconciliation;
    cursor_json the last-processed checkpoint for incremental pulls. The
    idempotency key makes retries safe: same key returns the same run."""
    __tablename__ = "import_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    source_system = Column(String, nullable=False)
    profile = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    source_hash = Column(String(64), nullable=False)
    status = Column(String, nullable=False, default="previewed")
    row_count = Column(Integer, nullable=False, default=0)
    imported = Column(Integer, nullable=False, default=0)
    skipped = Column(Integer, nullable=False, default=0)
    conflicted = Column(Integer, nullable=False, default=0)
    payload_json = Column(Text)
    cursor_json = Column(Text)
    report_json = Column(Text)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    confirmed_by = Column(String)
    confirmed_at = Column(DateTime)


class ImportConflict(Base):
    """One import row staff must decide. Nothing imports until resolved."""
    __tablename__ = "import_conflicts"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("import_runs.id"), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    source_record_id = Column(String, nullable=False)
    row_number = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    source_data_json = Column(Text)
    existing_invoice_id = Column(Integer, ForeignKey("invoices.id"))
    status = Column(String, nullable=False, default="open")
    resolution = Column(Text)
    resolved_by = Column(String)
    resolved_at = Column(DateTime)


class PaymentDiscrepancy(Base):
    """Money the provider reports that the ledger does not yet reflect.

    Kinds: refund_unposted, chargeback, settlement_short,
    settlement_unmatched, amount_mismatch. Resolution is always staff
    action; nothing here posts automatically."""
    __tablename__ = "payment_discrepancies"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    reference = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    expected_cents = Column(Integer)
    actual_cents = Column(Integer)
    currency = Column(String(3))
    event_id = Column(String)
    note = Column(Text)
    status = Column(String, nullable=False, default="open")
    resolution = Column(Text)
    resolved_by = Column(String)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SettlementLine(Base):
    """One provider settlement line matched against posted entries."""
    __tablename__ = "settlement_lines"
    __table_args__ = (UniqueConstraint("tenant_id", "provider",
                                       "settlement_ref", "payment_reference"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    settlement_ref = Column(String, nullable=False)
    payment_reference = Column(String, nullable=False)
    expected_cents = Column(Integer, nullable=False)
    settled_cents = Column(Integer, nullable=False)
    fee_cents = Column(Integer, nullable=False, default=0)
    currency = Column(String(3), nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MessageTemplate(Base):
    """Approved outbound template. Only approved bodies may send outside the
    24h service window or proactively. Meta-style {{1}} positional variables."""
    __tablename__ = "message_templates"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    language = Column(String, nullable=False, default="en")
    category = Column(String, nullable=False, default="utility")
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="draft")
    created_by = Column(String, nullable=False)
    approved_by = Column(String)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CommsPreference(Base):
    """Per-invoice channel consent. Proactive sends need an opted-in row."""
    __tablename__ = "comms_preferences"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id", "channel"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    channel = Column(String, nullable=False)
    opted_in = Column(Boolean, nullable=False, default=False)
    basis = Column(String, nullable=False, default="explicit")
    language = Column(String, nullable=False, default="en")
    updated_by = Column(String, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class PrivacyRequest(Base):
    """DPDP-style subject request (access/export/correction/deletion).

    Money and ledger identity are NEVER changed by this path: correction is
    limited to allowlisted contact fields, and deletion erases contact and
    communication data only. Financial records are retained under a
    books-of-account legal obligation. See app/services/privacy.py.
    """
    __tablename__ = "privacy_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)  # access, export, correction, deletion
    subject_type = Column(String, nullable=False)  # counterparty, staff_user
    subject_ref = Column(Integer, nullable=False)  # counterparty id / user id
    details = Column(Text)  # JSON: correction fields, scope notes
    status = Column(String, nullable=False, default="open")  # open, in_review, fulfilled, rejected
    resolution = Column(Text)  # outcome summary / rejection reason
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    decided_by = Column(String)
    decided_at = Column(DateTime)
