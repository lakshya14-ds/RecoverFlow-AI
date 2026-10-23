"""
RecoverFlow - Receivables and Collections
External Payment Gateway Plugin (Epic 2)
"""

class ExternalPayClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        
    def create_payment_intent(self, amount: float, currency: str, invoice_id: str) -> dict:
        """
        Create a payment link using a configured provider.
        """
        raise NotImplementedError("Payment provider is not configured")
        
    def schedule_ach_transfer(self, vendor_id: str, amount: float, date: str) -> dict:
        """
        Schedule an outgoing ACH transfer through a configured provider.
        """
        raise NotImplementedError("Payment provider is not configured")

pay_client = ExternalPayClient()
