"""
RecoverFlow - Receivables and Collections
"""
from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/health")
def health_check():
    """Confirm that the application and API are responding."""
    return {"status": "ok", "service": "RecoverFlow"}

@router.get("/config")
def get_config():
    """Return non-sensitive configuration values."""
    safe_config = {
        "HOST": settings.HOST,
        "PORT": settings.PORT,
        "LLM_MODEL": settings.LLM_MODEL,
        "DEBUG": settings.DEBUG,
        "AUTO_APPROVE_THRESHOLD": settings.AUTO_APPROVE_THRESHOLD,
        "FRAUD_ALERT_THRESHOLD": settings.FRAUD_ALERT_THRESHOLD,
        "DSO_FORECAST_HORIZON": settings.DSO_FORECAST_HORIZON
    }
    return safe_config
