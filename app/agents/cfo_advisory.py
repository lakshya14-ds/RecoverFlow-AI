"""
RecoverFlow - Receivables and Collections
CFO Advisory Agent (Epic 4)
"""
from typing import Dict, Any

def run_cfo_advisory(state: Dict[str, Any], dso_forecast: list) -> Dict[str, Any]:
    """
    Use DSO forecast data to produce plain-language cash flow suggestions.
    """
    # Mocking a basic logic for demonstration
    if not dso_forecast:
        return {"cfo_insights": ["Not enough data to generate cash flow insights."]}
        
    insights = []
    # Simple heuristic to mock LLM behavior based on DSO forecast
    if len(dso_forecast) > 0 and dso_forecast[-1].get("forecast_dso", 0) > 45:
        insights.append("Projected DSO is above 45 days. Consider earlier follow-up with the five customers with the largest overdue balances.")
    else:
        insights.append("Projected DSO is within the target range. Review supplier discounts before paying early.")
        
    return {
        "cfo_insights": insights
    }
