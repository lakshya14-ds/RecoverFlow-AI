from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/payments", tags=["payments"])

@router.post("/intent")
def create_payment_intent(amount: float, invoice_id: str):
    raise HTTPException(status_code=503, detail="Payment provider is not configured")

@router.post("/schedule")
def schedule_payment(vendor_id: str, amount: float, date: str):
    raise HTTPException(status_code=503, detail="Payment provider is not configured")
