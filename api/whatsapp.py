# api/whatsapp.py
from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import insert
from database.postgres import get_db
import hmac
import hashlib
from config.settings import settings
from models.user import User
from models.user_business import user_business
from models.business import PendingBusinessRequest, Business
from datetime import timezone, datetime
from utils.notification import send_whatsapp_notification

router = APIRouter()

@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle incoming WhatsApp messages."""
    # Verify webhook (Meta requirement)
    headers = request.headers
    signature = headers.get("X-Hub-Signature-256", "")
    body = await request.body()
    expected_signature = "sha256=" + hmac.new(
        settings.WHATSAPP_VERIFY_TOKEN.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    if signature != expected_signature:
        return {"status": "error", "message": "Invalid signature"}, 403

    data = await request.json()
    if "messages" not in data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}):
        return {"status": "ignored"}

    message = data["entry"][0]["changes"][0]["value"]["messages"][0]
    from_number = message["from"]  # e.g., "2348000000003" → normalize to "08000000003"
    body = message["text"]["body"].strip().lower()

    if from_number.startswith("234") and len(from_number) == 13:
        from_number = "0" + from_number[3:]

    customer = db.query(User).filter(User.phone_number == from_number).first()
    if not customer:
        return {"status": "error", "message": "User not found"}

    pending_request = db.query(PendingBusinessRequest).filter(
        PendingBusinessRequest.customer_id == customer.id
    ).order_by(PendingBusinessRequest.created_at.desc()).first()

    if not pending_request or pending_request.expires_at < datetime.now(timezone.utc):
        await send_whatsapp_notification(from_number, "No active invitation found or it has expired.")
        return {"status": "error", "message": "No active invitation"}

    business = db.query(Business).filter(Business.id == pending_request.business_id).first()
    try:
        if body == "accept":
            db.execute(insert(user_business).values(
                user_id=pending_request.customer_id,
                business_id=pending_request.business_id
            ))
            db.delete(pending_request)
            db.commit()
            await send_whatsapp_notification(from_number, f"You have successfully joined {business.name}!")
        elif body == "reject":
            db.delete(pending_request)
            db.commit()
            await send_whatsapp_notification(from_number, f"You have rejected the invitation to join {business.name}.")
        else:
            await send_whatsapp_notification(from_number, "Please reply with 'Accept' or 'Reject'.")
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}, 500

# Webhook verification (initial setup)
@router.get("/whatsapp/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge")
):
    if hub_mode == "subscribe" and hub_token == settings.WHATSAPP_VERIFY_TOKEN:
        return int(hub_challenge)
    return {"status": "error", "message": "Verification failed"}, 403