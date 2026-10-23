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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
