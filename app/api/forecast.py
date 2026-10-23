"""
RecoverFlow - Receivables and Collections
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.db_manager import get_db
from app.agents.dso_forecast import run_dso_agent
import pandas as pd
from app.database import models
from app.auth import Identity, get_identity

router = APIRouter(prefix="/forecast", tags=["Forecast"])

@router.get("/dso")
def get_dso_forecast(db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    # Build the forecast series from saved DSO snapshots.
    snapshots = db.query(models.DSOSnapshot).filter(
        models.DSOSnapshot.tenant_id == identity.tenant_id).order_by(
        models.DSOSnapshot.snapshot_date).all()
    
    if len(snapshots) < 30:
        return {"status": "warning", "message": "Not enough historical data (<30 days)", "forecast": []}
        
    df = pd.DataFrame([{"ds": s.snapshot_date, "y": s.dso_days} for s in snapshots])
    
    result = run_dso_agent({}, historical_df=df)
    return result
