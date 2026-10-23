"""
RecoverFlow - Receivables and Collections
"""
import sqlite3
import logging
from pathlib import Path
from app.config import settings

class AFISReader:
    """Read transactions from the AFIS database."""

    def __init__(self):
        self.db_path = Path(settings.AFIS_DB_PATH).resolve()

    def is_connected(self) -> bool:
        return self.db_path.exists()

    def get_transactions(
        self,
        start_date: str,
        end_date: str,
        tx_type: str = "both",
        limit: int = 1000
    ) -> list[dict]:
        """
        Read AFIS transactions within a date range.
        Return id, date, description, amount, and category.
        Positive amounts are income; negative amounts are expenses.
        """
        if not self.is_connected():
            return []

        if tx_type == "income":
            amount_filter = "AND amount > 0"
        elif tx_type == "expense":
            amount_filter = "AND amount < 0"
        else:
            amount_filter = ""

        query = f"""
            SELECT id, date, description, amount, category
            FROM transactions
            WHERE date BETWEEN ? AND ?
            {amount_filter}
            ORDER BY date DESC
            LIMIT ?
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, (start_date, end_date, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"AFIS read error: {e}")
            return []

    def get_unmatched_for_recoverflow(
        self,
        year: int,
        tx_type: str = "both"
    ) -> list[dict]:
        """
        Return AFIS transactions that have not yet been reconciled locally.
        """
        if not self.is_connected():
            return []
        
        # The caller must exclude already matched transactions.
        pass
