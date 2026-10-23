"""
RecoverFlow - Receivables and Collections
"""
from typing import Dict, Any
import pandas as pd
from app.ml.dso_prophet import dso_forecaster

def run_dso_agent(state: Dict[str, Any], historical_df: pd.DataFrame = None) -> Dict[str, Any]:
    """Generate a DSO forecast from historical snapshots."""
    if historical_df is None or historical_df.empty:
        return {"dso_forecast": []}
        
    forecast_data = dso_forecaster.generate_forecast(historical_df)
    
    return {
        "dso_forecast": forecast_data.get("forecast", [])
    }
