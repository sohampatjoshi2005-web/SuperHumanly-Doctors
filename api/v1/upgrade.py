from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api.v1.auth import get_current_user
from app.db import get_async_session
from app.db_models import UpgradeRequest, UsageMeter
from app.db_models import User
from app.services.email_service import send_email
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upgrade", tags=["upgrade"])

class UpgradeForm(BaseModel):
    full_name: str
    clinic_name: str
    phone_number: str

@router.get("/status")
async def get_trial_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get current trial status for the doctor.
    """
    meter = await session.get(UsageMeter, str(current_user.id))
    if not meter:
        # Fallback if meter wasn't initialized
        meter = UsageMeter(id=str(current_user.id))
        session.add(meter)
        await session.commit()
        await session.refresh(meter)

    from datetime import datetime, timedelta
    now = datetime.utcnow()
    
    # 7-day trial + 24h grace
    expiry_date = meter.trial_started_at + timedelta(days=8)
        
    days_left = (expiry_date - now).days
    
    return {
        "usage_count": meter.usage_count,
        "usage_limit": 10,
        "days_left": max(0, days_left),
        "is_unlimited": current_user.role == "admin" or current_user.is_unlimited,
        "is_expired": (meter.usage_count >= 10 or now > expiry_date) and not (current_user.role == "admin" or current_user.is_unlimited)
    }

@router.post("/request", status_code=status.HTTP_201_CREATED)
async def request_upgrade(
    payload: UpgradeForm,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Submit an upgrade request form.
    Persists to SQL and notifies the Superhumanly team.
    """
    # 1. Persist Request
    request = UpgradeRequest(
        doctor_id=str(current_user.id),
        full_name=payload.full_name,
        clinic_name=payload.clinic_name,
        phone_number=payload.phone_number
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    
    # 2. Notify Team
    subject = f"🚀 New Upgrade Request: {payload.clinic_name}"
    body = (
        f"New upgrade request received!\n\n"
        f"Doctor: {payload.full_name} (@{current_user.username})\n"
        f"Clinic: {payload.clinic_name}\n"
        f"Phone: {payload.phone_number}\n"
        f"Doctor ID: {current_user.id}\n"
        f"Submitted At: {request.requested_at}\n"
    )
    
    try:
        send_email(subject=subject, text_body=body)
        logger.info(f"Upgrade notification sent for clinic: {payload.clinic_name}")
    except Exception as e:
        logger.error(f"Failed to send upgrade notification: {e}")
        # We don't fail the request if email fails, as it's already in DB
    
    return {"message": "Upgrade request submitted successfully", "id": str(request.id)}
