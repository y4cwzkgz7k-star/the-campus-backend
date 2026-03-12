"""
Payment service placeholder.

When ready to integrate a payment provider (Stripe, CloudPayments, etc.),
implement the methods below. The Booking model already has:
  - payment_status: pending | paid | refunded | failed
  - payment_provider_id: str (provider's transaction/intent ID)
"""


class PaymentService:
    async def create_payment_intent(self, amount: float, currency: str, metadata: dict) -> str:
        """
        Create a payment intent with the provider.
        Returns provider's payment ID.
        """
        raise NotImplementedError("Payment provider not configured")

    async def confirm_payment(self, provider_payment_id: str) -> bool:
        raise NotImplementedError("Payment provider not configured")

    async def refund(self, provider_payment_id: str, amount: float | None = None) -> bool:
        raise NotImplementedError("Payment provider not configured")


payment_service = PaymentService()
