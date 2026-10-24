"""
RecoverFlow - Receivables and Collections
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.auth import authenticate, configured_keys
import logging
import os
from app.config import settings
from app.database.db_manager import init_db
from app.api.router import api_router
from app.services.intake_pipeline import process_one as process_intake_one, recover_interrupted_jobs
import asyncio

# Configure logging.
logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title="RecoverFlow",
    description="Invoice processing, reconciliation, collections, and receivables insights.",
    version="1.3.0"
)

@app.middleware("http")
async def protect_api(request: Request, call_next):
    # Public endpoints that do not require authentication
    public_paths = (
        "/api/v1/system/health",
        "/api/v1/auth/login",
    )
    if request.url.path.startswith("/api/v1/") and request.url.path not in public_paths:
        # Public callbacks perform their own raw-body provider signature verification.
        if (request.url.path.startswith("/api/v1/webhooks/razorpay/") or
                request.url.path.startswith("/api/v1/webhooks/meta-whatsapp/") or
                request.url.path.startswith("/api/v1/webhooks/shopify/")):
            return await call_next(request)
        
        # Extract credentials from X-API-KEY headers or Authorization: Bearer <token>
        raw_key = (
            request.headers.get("X-RECOVERFLOW-API-KEY")
            or request.headers.get("X-APEX-API-KEY", "")
        )
        if not raw_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                raw_key = auth_header[7:].strip()

        identity = authenticate(raw_key)
        if not identity:
            if not configured_keys() and not raw_key:
                return JSONResponse({"detail": "Set RECOVERFLOW_API_KEY before using the API"}, status_code=503)
            return JSONResponse({"detail": "Invalid or expired credentials"}, status_code=401)
        if request.method not in ("GET", "HEAD", "OPTIONS") and identity.role == "viewer":
            return JSONResponse({"detail": "Read-only account"}, status_code=403)
        request.state.identity = identity
    return await call_next(request)

@app.on_event("startup")
async def startup_event():
    logging.info("Starting RecoverFlow...")
    init_db()
    recover_interrupted_jobs()
    async def intake_loop():
        while True:
            try:
                worked = await asyncio.to_thread(process_intake_one)
                await asyncio.sleep(0.2 if worked else 2)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("Intake worker failed; retrying")
                await asyncio.sleep(2)
    app.state.intake_task = asyncio.create_task(intake_loop())


@app.on_event("shutdown")
async def stop_intake_loop():
    task = getattr(app.state, "intake_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app.include_router(api_router)

# Mount frontend
frontend_dir = os.path.join(settings.BASE_DIR, "frontend")
os.makedirs(frontend_dir, exist_ok=True)  # Ensure static assets are present.
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
