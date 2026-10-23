-- app/database/schema.sql

-- Invoices (AP = payable, AR = receivable)
CREATE TABLE IF NOT EXISTS invoices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id           TEXT NOT NULL DEFAULT 'local',
    invoice_number      TEXT NOT NULL,
    invoice_type        TEXT NOT NULL CHECK(invoice_type IN ('AP','AR')),
                                           -- AP = vendor payable, AR = customer receivable
    counterparty_name   TEXT NOT NULL,     -- vendor (AP) or customer (AR)
    counterparty_email  TEXT,
    counterparty_tax_id TEXT,              -- vendor or customer tax ID
    issue_date          DATE NOT NULL,
    due_date            DATE NOT NULL,
    received_date       DATE,              -- date received by RecoverFlow
    amount              REAL NOT NULL,     -- invoice amount before tax
    currency            TEXT DEFAULT 'USD',
    tax_amount          REAL DEFAULT 0.0,
    total_amount        REAL NOT NULL,     -- amount + tax_amount
    description         TEXT,
    po_number           TEXT,              -- related purchase order
    status              TEXT DEFAULT 'pending',
                        -- pending|matched|partially_matched|disputed|paid|overdue|cancelled
    source              TEXT DEFAULT 'manual',
                        -- manual|email|folder_watch|api_upload
    source_filename     TEXT,              -- original PDF filename
    source_path         TEXT,              -- path to stored PDF
    ocr_confidence      REAL DEFAULT 0.0, -- OCR confidence from 0.0 to 1.0
    ocr_raw_text        TEXT,              -- raw extracted text for diagnostics
    fraud_score         REAL DEFAULT 0.0, -- fraud risk score from 0.0 to 1.0
    is_duplicate        INTEGER DEFAULT 0,-- 0=no, 1=possible duplicate
    duplicate_of_id     INTEGER REFERENCES invoices(id),
    requires_human_review INTEGER DEFAULT 0,
    human_review_notes  TEXT,
    afis_transaction_id INTEGER,           -- AFIS transaction matched during reconciliation
    axis_classified     INTEGER DEFAULT 0, -- 1 if AXIS has classified the payment
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common lookups
CREATE INDEX IF NOT EXISTS idx_invoices_type_status ON invoices(invoice_type, status);
CREATE INDEX IF NOT EXISTS idx_invoices_due_date ON invoices(due_date);
CREATE INDEX IF NOT EXISTS idx_invoices_counterparty ON invoices(counterparty_name);
CREATE INDEX IF NOT EXISTS idx_invoices_fraud_score ON invoices(fraud_score);

-- Reconciliations between invoices and AFIS payments
CREATE TABLE IF NOT EXISTS reconciliations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id           TEXT NOT NULL DEFAULT 'local',
    invoice_id          INTEGER NOT NULL REFERENCES invoices(id),
    afis_transaction_id INTEGER NOT NULL,  -- AFIS transaction ID
    match_type          TEXT NOT NULL,     -- exact|fuzzy|partial|manual
    confidence_score    REAL NOT NULL,     -- match confidence from 0.0 to 1.0
    matched_amount      REAL NOT NULL,     -- amount actually reconciled
    variance_amount     REAL DEFAULT 0.0, -- difference: invoice.total - matched_amount
    variance_reason     TEXT,             -- e.g. early payment discount or partial payment
    match_date          DATETIME DEFAULT CURRENT_TIMESTAMP,
    matched_by          TEXT DEFAULT 'recoverflow_agent',
                        -- recoverflow_agent|human|axis_agent
    status              TEXT DEFAULT 'pending_review',
                        -- pending_review|approved|rejected
    reviewed_by_human   INTEGER DEFAULT 0,
    human_notes         TEXT,
    approved_at         DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reconciliations_invoice ON reconciliations(invoice_id);
CREATE INDEX IF NOT EXISTS idx_reconciliations_status ON reconciliations(status, confidence_score);

-- Collection campaigns for overdue receivables
CREATE TABLE IF NOT EXISTS dunning_campaigns (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id           TEXT NOT NULL DEFAULT 'local',
    invoice_id          INTEGER NOT NULL REFERENCES invoices(id),
    campaign_stage      INTEGER NOT NULL DEFAULT 1,
                        -- 1=friendly reminder, 2=formal notice, 3=final demand, 4=collections
    days_overdue        INTEGER NOT NULL DEFAULT 0,
    tone                TEXT NOT NULL,     -- friendly|formal|urgent|legal
    email_subject       TEXT,
    email_body          TEXT,
    email_to            TEXT,
    email_sent          INTEGER DEFAULT 0,
    email_sent_at       DATETIME,
    email_opened        INTEGER DEFAULT 0,
    email_opened_at     DATETIME,
    response_received   INTEGER DEFAULT 0,
    response_notes      TEXT,
    next_action_date    DATE,
    status              TEXT DEFAULT 'draft',
                        -- draft|scheduled|sent|responded|escalated|resolved
    generated_by        TEXT DEFAULT 'recoverflow_agent',
                        -- recoverflow_agent|human
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dunning_invoice ON dunning_campaigns(invoice_id);
CREATE INDEX IF NOT EXISTS idx_dunning_status ON dunning_campaigns(status, next_action_date);

-- Fraud alerts
CREATE TABLE IF NOT EXISTS fraud_alerts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id           TEXT NOT NULL DEFAULT 'local',
    invoice_id          INTEGER REFERENCES invoices(id),
    alert_type          TEXT NOT NULL,
                        -- duplicate|vendor_anomaly|amount_spike|new_vendor|bank_mismatch
    severity            TEXT NOT NULL,     -- low|medium|high|critical
    fraud_score         REAL NOT NULL,     -- 0.0–1.0
    description         TEXT NOT NULL,    -- human readable alert explanation
    features_flagged    TEXT,             -- JSON with the features behind the alert
    status              TEXT DEFAULT 'open',
                        -- open|investigating|resolved|false_positive
    investigated_by     TEXT,
    resolution_notes    TEXT,
    resolved_at         DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fraud_alerts_status ON fraud_alerts(status, severity);

-- DSO snapshots (Days Sales Outstanding)
CREATE TABLE IF NOT EXISTS dso_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id           TEXT NOT NULL DEFAULT 'local',
    snapshot_date       DATE NOT NULL,
    dso_days            REAL NOT NULL,     -- DSO calculated on this date
    ar_balance          REAL NOT NULL,     -- total open receivables
    revenue_30d         REAL NOT NULL,     -- revenue over the previous 30 days
    overdue_amount      REAL DEFAULT 0.0, -- total overdue receivables
    overdue_count       INTEGER DEFAULT 0,
    collection_rate     REAL DEFAULT 0.0, -- share of receivables collected in the period
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, snapshot_date)
);

-- Counterparty registry for vendors and customers
CREATE TABLE IF NOT EXISTS counterparties (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id           TEXT NOT NULL DEFAULT 'local',
    name                TEXT NOT NULL,
    type                TEXT NOT NULL CHECK(type IN ('vendor','customer','both')),
    email               TEXT,
    phone               TEXT,
    address             TEXT,
    tax_id              TEXT,              -- EIN / SSN
    payment_terms       INTEGER DEFAULT 30,-- default net 30 terms
    credit_limit        REAL DEFAULT 0.0,
    avg_payment_days    REAL DEFAULT 0.0, -- historical average days to pay
    on_time_rate        REAL DEFAULT 1.0, -- on time payment rate from 0.0 to 1.0
    total_invoiced      REAL DEFAULT 0.0,
    total_paid          REAL DEFAULT 0.0,
    fraud_flag          INTEGER DEFAULT 0, -- 0=ok, 1=suspicious, 2=blocked
    risk_score          REAL DEFAULT 0.0, -- aggregate risk score from 0.0 to 1.0
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, tax_id)
);

CREATE INDEX IF NOT EXISTS idx_counterparties_type ON counterparties(type, fraud_flag);

-- System settings (legacy table name retained for existing databases)
CREATE TABLE IF NOT EXISTS apex_settings (
    key                 TEXT PRIMARY KEY,
    value               TEXT NOT NULL,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings
INSERT OR IGNORE INTO apex_settings (key, value) VALUES
    ('dunning_stage1_days', '7'),       -- days overdue for a friendly reminder
    ('dunning_stage2_days', '15'),      -- days overdue for a formal notice
    ('dunning_stage3_days', '30'),      -- days overdue for a final demand
    ('dunning_stage4_days', '45'),      -- days overdue for collections escalation
    ('auto_approve_threshold', '0.90'), -- minimum confidence for automatic approval
    ('human_review_threshold', '0.60'), -- below this level manual review is required
    ('fraud_alert_threshold', '0.65'),  -- fraud score above this level creates an alert
    ('dso_target_days', '30'),          -- target DSO in days
    ('default_payment_terms', '30'),    -- default net 30 terms
    ('company_email', ''),              -- sender address for collection emails
    ('company_name', '');               -- company name in collection emails
