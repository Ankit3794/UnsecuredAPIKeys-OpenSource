from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import httpx
import structlog

from app.core.database import get_db
from app.core.config import settings
from app.models.database import DonationSupporter, DonationTracking

logger = structlog.get_logger()
router = APIRouter()


@router.post("/ipn")
async def process_ipn(request: Request, db: AsyncSession = Depends(get_db)):
    """Process PayPal IPN, matching C# PayPalIPNController.ProcessIPN"""
    try:
        # Read the raw IPN message from PayPal
        body = await request.body()
        ipn_message = body.decode('ascii')
        
        logger.info("Received PayPal IPN message")
        
        # Verify the IPN message with PayPal
        is_verified = await verify_ipn(ipn_message)
        
        if not is_verified:
            logger.warning("PayPal IPN verification failed", message=ipn_message)
            raise HTTPException(status_code=400, detail="IPN verification failed")
        
        # Parse the IPN message
        ipn_data = parse_query_string(ipn_message)
        
        # Extract key fields
        txn_id = ipn_data.get("txn_id")
        payment_status = ipn_data.get("payment_status")
        payer_email = ipn_data.get("payer_email")
        first_name = ipn_data.get("first_name")
        last_name = ipn_data.get("last_name")
        payer_id = ipn_data.get("payer_id")
        mc_gross = ipn_data.get("mc_gross")
        mc_currency = ipn_data.get("mc_currency")
        item_name = ipn_data.get("item_name")
        item_number = ipn_data.get("item_number")
        custom = ipn_data.get("custom")  # This could contain tracking ID
        
        logger.info("Processing PayPal IPN",
                   transaction_id=txn_id,
                   payer_email=payer_email,
                   payment_status=payment_status)
        
        # Only process completed payments
        if payment_status == "Completed":
            await process_completed_payment(
                db, txn_id, payer_email, first_name, last_name, 
                payer_id, mc_gross, mc_currency, custom
            )
        
        return {"status": "success"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing PayPal IPN", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


async def verify_ipn(ipn_message: str) -> bool:
    """Verify IPN message with PayPal"""
    try:
        # Prepare verification request
        verify_url = "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr"  # Sandbox
        if settings.paypal_mode == "live":
            verify_url = "https://ipnpb.paypal.com/cgi-bin/webscr"
        
        # Add cmd=_notify-validate to the original message
        verify_data = f"cmd=_notify-validate&{ipn_message}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                verify_url,
                data=verify_data.encode('ascii'),
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            result = response.text.strip()
            logger.debug("PayPal IPN verification result", result=result)
            
            return result == "VERIFIED"
            
    except Exception as e:
        logger.error("Error verifying PayPal IPN", error=str(e))
        return False


async def process_completed_payment(
    db: AsyncSession,
    txn_id: str,
    payer_email: str,
    first_name: str,
    last_name: str,
    payer_id: str,
    mc_gross: str,
    mc_currency: str,
    custom: str
):
    """Process completed payment"""
    try:
        from sqlalchemy import select
        
        # Check if transaction already exists
        query = select(DonationSupporter).where(DonationSupporter.TransactionId == txn_id)
        result = await db.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.info("Transaction already processed", transaction_id=txn_id)
            return
        
        # Convert amount to cents
        amount_usd_cents = int(float(mc_gross) * 100) if mc_gross else 0
        
        # Create donation supporter record
        supporter = DonationSupporter(
            PayerEmail=payer_email,
            PayerId=payer_id,
            FirstName=first_name,
            LastName=last_name,
            DonationAmountUSD=amount_usd_cents,
            DonationUTC=datetime.utcnow(),
            TransactionId=txn_id,
            IsPublic=False  # Default to private
        )
        
        db.add(supporter)
        
        # Update donation tracking if custom field contains tracking ID
        if custom:
            tracking_query = select(DonationTracking).where(
                DonationTracking.TrackingId == custom
            )
            tracking_result = await db.execute(tracking_query)
            tracking = tracking_result.scalar_one_or_none()
            
            if tracking:
                tracking.ConfirmedDonation = True
                logger.info("Donation tracking confirmed", tracking_id=custom)
        
        await db.commit()
        
        logger.info("Payment processed successfully",
                   transaction_id=txn_id,
                   amount_cents=amount_usd_cents,
                   payer_email=payer_email)
        
    except Exception as e:
        logger.error("Error processing completed payment", error=str(e))
        await db.rollback()
        raise


def parse_query_string(query_string: str) -> dict:
    """Parse URL-encoded query string into dictionary"""
    result = {}
    pairs = query_string.split('&')
    
    for pair in pairs:
        if '=' in pair:
            key, value = pair.split('=', 1)
            # URL decode the key and value
            key = key.replace('+', ' ')
            value = value.replace('+', ' ')
            # Simple URL decoding (for basic cases)
            result[key] = value
    
    return result