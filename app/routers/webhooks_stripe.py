"""
Stripe webhook handler.

Receives events from Stripe and updates booking payment_status accordingly.
Requires STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET in environment.
"""
import os

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/webhooks/stripe", tags=["webhooks"])


@router.post("/")
async def stripe_webhook(request: Request):
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    # Read per-request so the value is picked up after module load (e.g. runtime secrets injection)
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise HTTPException(status_code=400, detail="Webhook secret not configured")

    try:
        import stripe  # type: ignore
        client = stripe.StripeClient(stripe_key)
    except ImportError:
        raise HTTPException(status_code=503, detail="stripe library not installed")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        # Use client.webhooks (new SDK style) consistent with StripeClient usage
        event = client.webhooks.construct_event(payload, sig_header, webhook_secret)
    except stripe.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Webhook parse error: {exc}")

    event_type: str = event.get("type", "")

    # Import DB utilities lazily to avoid circular imports at module load
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.booking import Booking

    if event_type == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        provider_id: str = payment_intent["id"]

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Booking).where(Booking.payment_provider_id == provider_id)
            )
            booking = result.scalar_one_or_none()
            if booking and booking.payment_status != "paid":
                booking.payment_status = "paid"
                await db.commit()

    elif event_type == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        provider_id = payment_intent["id"]

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Booking).where(Booking.payment_provider_id == provider_id)
            )
            booking = result.scalar_one_or_none()
            if booking and booking.payment_status not in ("paid", "failed"):
                booking.payment_status = "failed"
                await db.commit()

    elif event_type == "charge.refunded":
        charge = event["data"]["object"]
        payment_intent_id: str = charge.get("payment_intent", "")
        if payment_intent_id:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Booking).where(Booking.payment_provider_id == payment_intent_id)
                )
                booking = result.scalar_one_or_none()
                if booking:
                    booking.payment_status = "refunded"
                    booking.refund_status = "completed"
                    await db.commit()

    # Return 200 for all other events to acknowledge receipt
    return {"received": True, "type": event_type}
