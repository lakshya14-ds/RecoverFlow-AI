"""
RecoverFlow - Receivables and Collections
"""
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    APEX_DB_PATH: str = "apex_ar.db"
    AFIS_DB_PATH: str = "../AFIS/afis_finance.db"   # path relative to the parent project
    AXIS_DB_PATH: str = "../AXIS/axis_tax.db"        # reads payment classifications
    PDF_STORAGE_PATH: str = "data/invoices"          # local invoice storage

    # LLM
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-3-5-sonnet-20241022"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.3            # controlled variation for collection drafts

    # OCR (Tesseract)
    TESSERACT_CMD: str = "tesseract"        # path to the Tesseract executable
    OCR_LANG: str = "eng"                   # default OCR language
    OCR_DPI: int = 300                      # resolution for PDF to image conversion

    # ML Models
    ML_MODELS_PATH: str = "app/ml/models"
    FRAUD_CONTAMINATION: float = 0.05       # assumed anomaly rate for Isolation Forest
    FRAUD_ALERT_THRESHOLD: float = 0.65     # scores above this level create an alert
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
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
