"""KYC (Know Your Customer) service — Smile ID biometric verification.

Two flows:
  - initiate_kyc()  : pre-signup, no auth. Returns a reference_token that the
                      signup endpoint consumes (agents/sub-agents).
  - complete_kyc()  : post-signup, authenticated. Directly updates the user's
                      kyc_status (customers).

Dev mode (SMILE_PARTNER_ID not set): all verifications auto-pass.
"""

import hmac
import hashlib
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from config.settings import settings
from models.user import KycVerification, User
from schemas.user import KycVerifyRequest, KycCompleteRequest
from utils.response import success_response, error_response
from store.repositories.user import UserRepository

logger = logging.getLogger(__name__)

SMILE_SANDBOX_URL = "https://testapi.smileidentity.com/v1"
SMILE_PROD_URL = "https://api.smileidentity.com/v1"


def _smile_base_url() -> str:
    return SMILE_SANDBOX_URL if settings.SMILE_SANDBOX else SMILE_PROD_URL


def _build_signature(timestamp: str) -> str:
    """HMAC-SHA256 signature expected by Smile ID."""
    partner_id = settings.SMILE_PARTNER_ID or ""
    api_key = settings.SMILE_API_KEY or ""
    msg = f"{timestamp}{partner_id}".encode()
    return hmac.new(api_key.encode(), msg, hashlib.sha256).hexdigest()


async def _call_smile_id(
    id_type: str,
    id_number: str,
    selfie_base64: str,
    full_name: str,
) -> Tuple[bool, str, str]:
    """
    Call Smile ID Enhanced KYC with a selfie.

    Returns:
        (passed: bool, smile_reference: str, result_text: str)
    """
    # --- Dev mode: no keys configured ---
    if not settings.SMILE_PARTNER_ID:
        logger.info("[KYC] Dev mode — auto-passing KYC (SMILE_PARTNER_ID not set)")
        return True, "DEV_REF_" + secrets.token_hex(8), "Dev mode — KYC bypassed"

    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    name_parts = full_name.strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    payload = {
        "partner_id": settings.SMILE_PARTNER_ID,
        "signature": _build_signature(timestamp),
        "timestamp": timestamp,
        "country": "NG",
        "id_type": id_type,
        "id_number": id_number,
        "first_name": first_name,
        "last_name": last_name,
        "selfie_image": selfie_base64,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{_smile_base_url()}/id_verification", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("[KYC] Smile ID HTTP error: %s — %s", exc.response.status_code, exc.response.text)
        return False, "", f"Verification service error ({exc.response.status_code})"
    except Exception as exc:
        logger.error("[KYC] Smile ID request failed: %s", exc)
        return False, "", "Could not reach verification service. Please try again."

    # Smile ID result codes: 1020 = exact match, 1021 = partial match (also acceptable)
    result_code = str(data.get("ResultCode", ""))
    result_text = data.get("ResultText", "Verification failed")
    smile_ref = data.get("SmileJobID", "")
    passed = result_code in ("1020", "1021")

    logger.info(
        "[KYC] Smile ID result: code=%s text=%s ref=%s passed=%s",
        result_code, result_text, smile_ref, passed,
    )
    return passed, smile_ref, result_text


async def initiate_kyc(request: KycVerifyRequest, db: Session):
    """
    Pre-signup KYC for agents/sub-agents.
    Calls Smile ID and, on success, stores a short-lived reference_token
    that the signup endpoint must present to prove KYC was completed.
    """
    passed, smile_ref, result_text = await _call_smile_id(
        id_type=request.id_type,
        id_number=request.id_number,
        selfie_base64=request.selfie_image,
        full_name=request.full_name,
    )

    token = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    record = KycVerification(
        phone_number=request.phone_number,
        id_type=request.id_type,
        id_number=request.id_number,
        full_name=request.full_name,
        status="passed" if passed else "failed",
        smile_reference=smile_ref,
        result_text=result_text,
        reference_token=token,
        used=False,
        expires_at=now + timedelta(minutes=30),
    )
    db.add(record)
    db.commit()

    if not passed:
        raise HTTPException(
            status_code=400,
            detail=result_text or "Identity verification failed. Please check your details and try again.",
        )

    return success_response(
        status_code=200,
        message="Identity verified successfully",
        data={"reference_token": token},
    )


async def complete_kyc(request: KycCompleteRequest, current_user: dict, db: Session):
    """
    Post-signup KYC for customers (from their Settings page).
    Calls Smile ID and directly updates the user's kyc_status.
    """
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.kyc_status == "verified":
        return success_response(
            status_code=200,
            message="Your identity is already verified",
            data={"kyc_status": "verified"},
        )

    passed, smile_ref, result_text = await _call_smile_id(
        id_type=request.id_type,
        id_number=request.id_number,
        selfie_base64=request.selfie_image,
        full_name=request.full_name,
    )

    user.kyc_status = "verified" if passed else "failed"
    db.commit()
    db.refresh(user)

    if not passed:
        raise HTTPException(
            status_code=400,
            detail=result_text or "Identity verification failed. Please check your details and try again.",
        )

    return success_response(
        status_code=200,
        message="Identity verified successfully",
        data={"kyc_status": "verified"},
    )


def validate_and_consume_kyc_reference(reference_token: str, db: Session) -> KycVerification:
    """
    Used by the signup service to validate and consume a kyc_reference.
    Raises HTTPException on any failure.
    Returns the KycVerification record (already marked as used).
    """
    record = db.query(KycVerification).filter(
        KycVerification.reference_token == reference_token
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="Invalid KYC reference token")
    if record.used:
        raise HTTPException(status_code=400, detail="KYC reference has already been used")
    if record.status != "passed":
        raise HTTPException(status_code=400, detail="KYC verification was not successful")
    if record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="KYC reference has expired. Please verify again.")

    record.used = True
    db.commit()
    return record
