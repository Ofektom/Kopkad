import httpx
from fastapi import HTTPException
from utils.response import error_response
from config.settings import settings
from decimal import Decimal
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Comment out the real Paystack implementation
# async def initiate_virtual_account_payment(amount: Decimal, email: str, customer_id: int, reference: str):
#     """Create a one-time Dedicated Virtual Account for payment."""
#     async with httpx.AsyncClient() as client:
#         # Step 1: Create a customer if not already created (optional, can skip if customer exists)
#         customer_response = await client.post(
#             "https://api.paystack.co/customer",
#             headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
#             json={
#                 "email": email,
#                 "first_name": "Customer",
#                 "last_name": str(customer_id),
#             }
#         )
#         customer_data = customer_response.json()
#         if not customer_data["status"]:
#             logger.error(f"Customer creation failed: {customer_data['message']}")
#             return error_response(status_code=400, message=customer_data["message"])
#         customer_code = customer_data["data"]["customer_code"]

#         # Step 2: Create a Dedicated Virtual Account
#         dva_response = await client.post(
#             "https://api.paystack.co/dedicated_account",
#             headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
#             json={
#                 "customer": customer_code,
#                 "preferred_bank": "test-bank",  # Use "wema-bank" or "test-bank" in test mode
#                 "expires_at": (datetime.now() + timedelta(days=1)).isoformat()  # One-time, expires in 24 hours
#             }
#         )
#         dva_data = dva_response.json()
#         if not dva_data["status"]:
#             logger.error(f"DVA creation failed: {dva_data['message']}")
#             return error_response(status_code=400, message=dva_data["message"])

#         account_details = dva_data["data"]
#         logger.info(f"Virtual account created: {account_details['account_number']} for {reference}")
#         return {
#             "account_number": account_details["account_number"],
#             "bank_name": account_details["bank"]["name"],
#             "amount": amount,
#             "reference": reference,
#             "expires_at": account_details["expires_at"]
#         }

# Add the mock implementation
async def initiate_virtual_account_payment(amount: Decimal, email: str, customer_id: int, reference: str) -> dict:
    """
    Mock function for testing bank transfer without Paystack.
    """
    virtual_account = {
        "account_number": f"9876543210-{reference[-6:]}",
        "bank_name": "Test Bank",
        "reference": reference,
        "amount": int(amount * 100),  # Kobo
        "expires_at": (datetime.now() + timedelta(days=1)).isoformat()  # Mimics real response
    }
    logger.info(f"Mock virtual account created: {virtual_account['account_number']} for {reference}")
    return virtual_account

# Keep the verify_payment function as-is (for card payments or future use)
async def verify_payment(reference: str, expected_amount: Decimal):
    """Verify payment (for manual testing, optional)."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
        )
        data = response.json()
        if not data["status"] or data["data"]["status"] != "success":
            logger.error(f"Payment verification failed: {data.get('message', 'No message')}")
            return error_response(status_code=400, message="Payment verification failed")
        paid_amount = Decimal(data["data"]["amount"]) / 100
        if paid_amount < expected_amount:
            logger.error(f"Underpayment: expected {expected_amount}, paid {paid_amount}")
            return error_response(status_code=400, message=f"Paid amount {paid_amount} less than expected {expected_amount}")
        logger.info(f"Payment verified: {reference}")
        return reference


        #interswitch flutterwave