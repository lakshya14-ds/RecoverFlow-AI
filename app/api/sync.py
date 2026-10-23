from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/sync", tags=["sync"])

@router.post("/erp")
def force_erp_sync():
    raise HTTPException(status_code=503, detail="Accounting provider is not configured")

@router.get("/chart-of-accounts")
def get_chart_of_accounts():
    raise HTTPException(status_code=503, detail="Accounting provider is not configured")
