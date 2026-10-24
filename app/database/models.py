"""
RecoverFlow - Receivables and Collections
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.db_manager import Base

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
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    received_date = Column(Date)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    tax_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
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
    matched_amount = Column(Float, nullable=False)
    variance_amount = Column(Float, default=0.0)
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
    __table_args__ = (UniqueConstraint("tenant_id", "source", "reference"),)
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    amount_cents = Column(Integer, nullable=False)
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
    ar_balance = Column(Float, nullable=False)
    revenue_30d = Column(Float, nullable=False)
    overdue_amount = Column(Float, default=0.0)
    overdue_count = Column(Integer, default=0)
    collection_rate = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Counterparty(Base):
    """
    Represents a business entity (Vendor or Customer).
    """
    __tablename__ = "counterparties"
    __table_args__ = (UniqueConstraint("tenant_id", "tax_id"),)
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, default="local", index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    address = Column(Text)
    tax_id = Column(String)
    payment_terms = Column(Integer, default=30)
    credit_limit = Column(Float, default=0.0)
    avg_payment_days = Column(Float, default=0.0)
    on_time_rate = Column(Float, default=1.0)
    total_invoiced = Column(Float, default=0.0)
    total_paid = Column(Float, default=0.0)
    fraud_flag = Column(Integer, default=0)
    risk_score = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


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
    """Source-linked evidence verifying amounts, POs, dispute claims, or bank entries."""
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
