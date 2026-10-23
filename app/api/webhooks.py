from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.post("/inbound")
async def receive_inbound_message():
    """Webhook for incoming messages (WhatsApp, Email) to trigger Multichannel Ingestion."""
    raise HTTPException(status_code=503, detail="Inbound provider is not configured")
