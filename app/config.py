"""
RecoverFlow - Receivables and Collections
"""
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Paths & Database
    BASE_DIR: Path = Path(__file__).parent.parent
    DATABASE_URL: str = ""                           # If set (e.g. postgresql://...), overrides APEX_DB_PATH
    APEX_DB_PATH: str = "apex_ar.db"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    AFIS_DB_PATH: str = "../AFIS/afis_finance.db"   # path relative to the parent project
    AXIS_DB_PATH: str = "../AXIS/axis_tax.db"        # reads payment classifications
    PDF_STORAGE_PATH: str = "data/invoices"          # local invoice storage
    INTAKE_STORAGE_PATH: str = "data/intake"         # durable intake evidence
    INCOMING_STORAGE_PATH: str = "data/incoming"     # temporary invoice upload staging
    AUTH_TOKEN_EXPIRE_HOURS: int = 24

    # LLM
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-3-5-sonnet-20241022"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.3            # controlled variation for collection drafts
    GEMINI_API_KEY: str = ""
    GEMINI_API_KEY_1: str = ""
    GEMINI_API_KEY_2: str = ""
    GEMINI_API_KEY_3: str = ""
    # JSON role-to-slot mapping, e.g. {"intake":1,"drafter":2,"negotiator":3}.
    GEMINI_ROLE_MAP_JSON: str = ""
    GEMINI_KEY_3_RESERVE_RPM: int = 5
    GEMINI_KEY_3_RESERVE_RPD: int = 300
    AGENT_MODEL: str = "gemini-3.6-flash"
    GEMINI_RPM_LIMIT: int = 15              # Requested per-slot client cap
    GEMINI_RPD_LIMIT: int = 1500            # Requested per-slot client cap

    # OCR (Tesseract)
    TESSERACT_CMD: str = "tesseract"        # path to the Tesseract executable
    OCR_LANG: str = "eng"                   # default OCR language
    OCR_DPI: int = 300                      # resolution for PDF to image conversion

    # ML Models
    ML_MODELS_PATH: str = "app/ml/models"
    FRAUD_CONTAMINATION: float = 0.05       # assumed anomaly rate for Isolation Forest
    FRAUD_ALERT_THRESHOLD: float = 0.65     # scores above this level create an alert
    DSO_TARGET_DAYS: int = 30               # target DSO in days
    DSO_FORECAST_HORIZON: int = 90          # DSO forecast horizon in days

    # Reconciliation
    AUTO_APPROVE_THRESHOLD: float = 0.90    # confidence at or above 0.90 allows approval
    HUMAN_REVIEW_THRESHOLD: float = 0.60    # confidence below 0.60 requires manual review

    # Collection email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = ""                    # sender address for collection emails
    EMAIL_DRY_RUN: bool = True              # True prevents actual delivery

    # Collection stages in days after the due date
    DUNNING_STAGE1_DAYS: int = 7
    DUNNING_STAGE2_DAYS: int = 15
    DUNNING_STAGE3_DAYS: int = 30
    DUNNING_STAGE4_DAYS: int = 45
    CONTACT_COOLDOWN_DAYS: int = 7

    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8002                        # separate from AFIS (8000) and AXIS (8001)
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    APEX_API_KEY: str = ""
    APEX_API_KEYS_JSON: str = ""
    RECOVERFLOW_API_KEY: str = ""
    RECOVERFLOW_API_KEYS_JSON: str = ""
    FRONTEND_ORIGINS: str = ""                 # Comma-separated HTTPS origins for a separately hosted frontend
    ADMIN_BOOTSTRAP_PASSWORD: str = ""         # Optional initial admin password; never use a fixed default
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    POPPLER_PATH: str = ""

    # Release 2 providers. No provider call is enabled without its own credentials.
    SHOPIFY_SHOP_DOMAIN: str = ""
    SHOPIFY_ADMIN_ACCESS_TOKEN: str = ""
    SHOPIFY_API_VERSION: str = "2026-07"
    SHOPIFY_WEBHOOK_SECRET: str = ""
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_MODE: str = "test"
    META_WHATSAPP_ACCESS_TOKEN: str = ""
    META_WHATSAPP_PHONE_NUMBER_ID: str = ""
    META_WHATSAPP_APP_SECRET: str = ""
    META_WHATSAPP_VERIFY_TOKEN: str = ""
    META_GRAPH_API_VERSION: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
