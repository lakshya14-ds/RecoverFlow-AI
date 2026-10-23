"""
RecoverFlow - Receivables and Collections
"""
import numpy as np
from sklearn.ensemble import IsolationForest
import pandas as pd
from app.config import settings
import logging

class FraudDetector:
    """Detect invoice amount anomalies with Isolation Forest."""
    
    def __init__(self):
        self.contamination = settings.FRAUD_CONTAMINATION
        self.model = IsolationForest(contamination=self.contamination, random_state=42)
        self.is_fitted = False

    def fit(self, df: pd.DataFrame):
        """Fit the model using historical invoices."""
        if df.empty or len(df) < 10:
            logging.info("Not enough data to train Isolation Forest.")
            return
            
        features = self._extract_features(df)
        self.model.fit(features)
        self.is_fitted = True

    def predict_score(self, invoice_dict: dict) -> dict:
        """Return an anomaly score from 0 to 1 and flagged features."""
        if not self.is_fitted:
            return {"fraud_score": 0.0, "features_flagged": []}

        try:
            df = pd.DataFrame([invoice_dict])
            features = self._extract_features(df)
            
            # Lower decision scores indicate more unusual values.
            score_raw = self.model.decision_function(features)[0]
            
            # Normalize to 0-1, where higher values indicate greater anomaly.
            score_norm = 0.5 - (score_raw / 2)
            score_norm = max(0.0, min(1.0, score_norm))
            
            flagged = []
            if score_norm > settings.FRAUD_ALERT_THRESHOLD:
                flagged.append("anomaly_detected")

            return {"fraud_score": float(score_norm), "features_flagged": flagged}
        except Exception as e:
            logging.error(f"Failed to calculate anomaly score: {e}")
            return {"fraud_score": 0.0, "features_flagged": []}

    def _extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract numeric model features."""
        X = pd.DataFrame()
        X['amount'] = df.get('total_amount', pd.Series([0.0])).fillna(0.0).astype(float)
        # Future features could include time until due and vendor amount variance.
        return X

fraud_detector = FraudDetector()
