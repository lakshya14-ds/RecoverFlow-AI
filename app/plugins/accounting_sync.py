"""
RecoverFlow - Receivables and Collections
Accounting Sync Plugin (Epic 1)
"""

class AccountingSyncClient:
    def __init__(self, token: str = None):
        self.token = token
        
    def sync_invoices_to_erp(self, invoices: list) -> dict:
        """
        Sync approved invoices to a configured accounting platform.
        """
        raise NotImplementedError("Accounting provider is not configured")
        
    def fetch_chart_of_accounts(self) -> list:
        """
        Fetch the external chart of accounts.
        """
        raise NotImplementedError("Accounting provider is not configured")

accounting_client = AccountingSyncClient()
