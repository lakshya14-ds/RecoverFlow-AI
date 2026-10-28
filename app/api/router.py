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
from .policies import router as policies_router
from .messages import router as messages_router
from .integrations import router as integrations_router
from .controlled_agent import router as controlled_agent_router
from .auth import router as auth_router
from .intake import router as intake_router
from .negotiations import router as negotiations_router
from .supervisor import router as supervisor_router
from .allocations import router as allocations_router

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
api_router.include_router(policies_router)
api_router.include_router(messages_router)
api_router.include_router(integrations_router)
api_router.include_router(controlled_agent_router)
api_router.include_router(auth_router)
api_router.include_router(intake_router)
api_router.include_router(negotiations_router)
api_router.include_router(supervisor_router)
api_router.include_router(allocations_router)
