"""
RecoverFlow - Receivables and Collections
"""
from fastapi import APIRouter

from .invoices import router as invoices_router
from .reconciliation import router as reconciliation_router
from .dunning import router as dunning_router
from .fraud import router as fraud_router
from .forecast import router as forecast_router
from .reports import router as reports_router
from .system import router as system_router
from .payments import router as payments_router
from .sync import router as sync_router
from .webhooks import router as webhooks_router
from .cases import router as cases_router
from .imports import router as imports_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(invoices_router)
api_router.include_router(reconciliation_router)
api_router.include_router(dunning_router)
api_router.include_router(fraud_router)
api_router.include_router(forecast_router)
api_router.include_router(reports_router)
api_router.include_router(system_router)
api_router.include_router(payments_router)
api_router.include_router(sync_router)
api_router.include_router(webhooks_router)
api_router.include_router(cases_router)
api_router.include_router(imports_router)
