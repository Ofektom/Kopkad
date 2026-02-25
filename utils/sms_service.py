# utils/sms_service.py
import httpx
import os
from typing import Dict, Any
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

TERMII_API_KEY = os.getenv("TERMII_API_KEY")
TERMII_SENDER_ID = os.getenv("TERMII_SENDER_ID") or "Kopkad"
TERMII_BASE_URL = "https://v3.api.termii.com/api/sms/send"  # Updated based on your provided URL

def normalize_phone(phone: str) -> str:
    """Normalize phone to international format (+234...) for Termii."""
    cleaned = phone.strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("0"):
        return "+234" + cleaned[1:]
    if cleaned.startswith("234"):
        return "+" + cleaned
    if not cleaned.startswith("+"):
        return "+234" + cleaned
    return cleaned

async def send_termii_sms_async(to_phone: str, message: str) -> Dict[str, Any]:
    """
    Send SMS via Termii asynchronously.
    Returns: {'status': 'success'|'error', 'message': str, 'data': dict}
    """
    if not TERMII_API_KEY:
        logger.error("TERMII_API_KEY not set in .env")
        return {"status": "error", "message": "SMS service not configured"}

    phone = normalize_phone(to_phone)
    payload = {
        "to": phone,
        "from": TERMII_SENDER_ID,
        "sms": message,
        "type": "plain",
        "channel": "generic",
        "api_key": TERMII_API_KEY,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(TERMII_BASE_URL, json=payload, timeout=15.0)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success":
                logger.info(f"SMS sent to {phone}: {message[:50]}...")
                return {"status": "success", "message": "SMS sent successfully", "data": data}
            else:
                error_msg = data.get("message", "Unknown Termii error")
                logger.error(f"Termii failed: {error_msg}")
                return {"status": "error", "message": error_msg}

        except httpx.HTTPStatusError as e:
            error_msg = f"Termii HTTP {e.response.status_code}: {e.response.text}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        except Exception as e:
            logger.exception("Termii SMS exception")
            return {"status": "error", "message": f"Failed to send SMS: {str(e)}"}