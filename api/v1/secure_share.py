from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from jose import JWTError, jwt
from app.core.config import settings
from app.api.v1.auth import get_current_user
from app.db_models import User
from app.db import get_session
from app.db_models import Encounter, Customer, User, Clinic
from sqlmodel import select
from app.services.audit_service import log_audit_batched

router = APIRouter(prefix="/share", tags=["secure_share"])

def create_share_token(encounter_id: str, expires_delta: timedelta = timedelta(days=7)):
    expire = datetime.utcnow() + expires_delta
    to_encode = {"sub": encounter_id, "type": "secure_share", "exp": expire}
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded_jwt

@router.post("/generate/{encounter_id}")
async def generate_share_link(
    encounter_id: str,
    current_user: User = Depends(get_current_user)
):
    with get_session() as session:
        enc = session.get(Encounter, encounter_id)
        if not enc or enc.doctor_id != current_user.id:
            raise HTTPException(status_code=404, detail="Encounter not found or access denied")
        
        token = create_share_token(encounter_id)
        # Assuming frontend runs on same domain or we append a base URL
        # For this setup, we just return the token and the frontend can construct the full URL
        # e.g., https://superhumanlydoctors.io/share/{token}
        return {
            "status": "success",
            "token": token,
            "expires_in_days": 7
        }

@router.get("/view/{token}")
async def view_shared_encounter(token: str):
    """
    Publicly accessible endpoint that uses a cryptographic token to grant time-limited 
    read-only access to a specific clinical summary.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired share token",
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        encounter_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if not encounter_id or token_type != "secure_share":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    with get_session() as session:
        enc = session.get(Encounter, encounter_id)
        if not enc:
            raise HTTPException(status_code=404, detail="Encounter not found")
            
        customer = session.get(Customer, enc.customer_id)
        doctor = session.get(User, enc.doctor_id)
        clinic = session.get(Clinic, enc.clinic_id) if enc.clinic_id else None
        
        # Log Access Event (Async Audit)
        import asyncio
        asyncio.create_task(log_audit_batched(
            actor="Patient/Link-Bearer",
            action="SECURE_SHARE_ACCESSED",
            resource_type="Encounter",
            resource_id=encounter_id,
            clinic_id=enc.clinic_id,
            extra_metadata={"token_view": True}
        ))
        
        # Return only the safe, necessary data for the patient
        return {
            "doctor_name": doctor.username if doctor else "Your Physician", 
            "clinic_name": clinic.name if clinic else "Private Practice",
            "patient_name": customer.name if customer else "Unknown",
            "date": enc.created_at,
            "patient_summary": enc.patient_summary,
            "prescription": enc.rx_json,
            "prescription_text": enc.rx_text
        }
