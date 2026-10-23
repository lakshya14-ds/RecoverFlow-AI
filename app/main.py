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

# Configure logging.
logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title="RecoverFlow",
    description="Invoice processing, reconciliation, collections, and receivables insights.",
    version="1.2.0"
)

@app.middleware("http")
async def protect_api(request: Request, call_next):
    if request.url.path.startswith("/api/v1/") and request.url.path != "/api/v1/system/health":
        if not configured_keys():
            return JSONResponse({"detail": "Set RECOVERFLOW_API_KEY before using the API"}, status_code=503)
        identity = authenticate(request.headers.get("X-RECOVERFLOW-API-KEY")
                                or request.headers.get("X-APEX-API-KEY", ""))
        if not identity:
            return JSONResponse({"detail": "Invalid API key"}, status_code=401)
        if request.method not in ("GET", "HEAD", "OPTIONS") and identity.role == "viewer":
            return JSONResponse({"detail": "Read-only account"}, status_code=403)
        request.state.identity = identity
    return await call_next(request)

@app.on_event("startup")
def startup_event():
    logging.info("Starting RecoverFlow...")
    init_db()

app.include_router(api_router)

# Mount frontend
frontend_dir = os.path.join(settings.BASE_DIR, "frontend")
os.makedirs(frontend_dir, exist_ok=True)  # Ensure static assets are present.
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
