from typing import Optional, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlmodel import select
from app.api.v1.auth import get_current_user
from app.db_models import User
from app.db import get_session, scoped_select
from app.db_models import Encounter
from app.services.audit_service import log_audit_batched


router = APIRouter(prefix="/encounters", tags=["encounters"])


@router.get("/batch")
async def get_batch_encounters(
    customer_ids: str,  # Comma-separated customer IDs
    request: Request,
    current_user: User = Depends(get_current_user)
):
    try:
        ids = [id.strip() for id in customer_ids.split(',') if id.strip()]
        if not ids:
            return []
        
        with get_session() as session:
            statement = scoped_select(Encounter).where(Encounter.customer_id.in_(ids))
            
            # PERMISSION FILTER
            if current_user.role == "doctor":
                statement = statement.where(Encounter.doctor_id == str(current_user.id))
            elif current_user.role == "admin":
                statement = select(Encounter).where(Encounter.customer_id.in_(ids)) # Master admin bypasses scope
            
            statement = statement.order_by(Encounter.created_at.desc())
            encounters = session.exec(statement).all()
            
            client_ip = request.client.host if request.client else "unknown"
            await log_audit_batched(
                actor=current_user.username, action="READ_BATCH_ENCOUNTERS",
                resource_type="Encounter", resource_id=f"batch_{len(ids)}_customers",
                ip_address=client_ip, extra_metadata={"clinic_id": current_user.clinic_id}
            )
            return encounters
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid customer_ids format: {e}")


@router.get("/{encounter_id}", response_model=Encounter)
async def get_encounter(
    encounter_id: str, 
    request: Request,
    current_user: User = Depends(get_current_user)
) -> Encounter:
    with get_session() as session:
        enc = session.get(Encounter, encounter_id)
        if not enc:
             raise HTTPException(status_code=404, detail="encounter not found")
        
        # PERMISSION CHECK
        is_owner = enc.doctor_id == str(current_user.id)
        is_clinic_admin = current_user.role == "clinic_admin" and enc.clinic_id == current_user.clinic_id
        is_master_admin = current_user.role == "admin"

        if not (is_owner or is_clinic_admin or is_master_admin):
            raise HTTPException(status_code=403, detail="Access denied to this clinical encounter")
        
        client_ip = request.client.host if request.client else "unknown"
        await log_audit_batched(
            actor=current_user.username, action="READ_ENCOUNTER",
            resource_type="Encounter", resource_id=encounter_id,
            ip_address=client_ip, extra_metadata={"doctor_id": current_user.id}
        )
        return enc


class EncounterUpdate(BaseModel):
    codes_json: Optional[Dict[str, Any]] = None
    patient_summary: Optional[str] = None
    rx_text: Optional[str] = None


@router.patch("/{encounter_id}", response_model=Encounter)
async def update_encounter(
    encounter_id: str,
    payload: EncounterUpdate,
    request: Request,
    current_user: User = Depends(get_current_user)
) -> Encounter:
    with get_session() as session:
        enc = session.get(Encounter, encounter_id)
        if not enc:
             raise HTTPException(status_code=404, detail="encounter not found")
        
        # UPDATE PERMISSION CHECK (Only the owner or clinic admin can update)
        is_owner = enc.doctor_id == str(current_user.id)
        is_clinic_admin = current_user.role == "clinic_admin" and enc.clinic_id == current_user.clinic_id

        if not (is_owner or is_clinic_admin):
            raise HTTPException(status_code=403, detail="Access denied: Cannot update colleague's record")
        
        if payload.codes_json is not None: enc.codes_json = payload.codes_json
        if payload.patient_summary is not None: enc.patient_summary = payload.patient_summary
        if payload.rx_text is not None: enc.rx_text = payload.rx_text
            
        session.add(enc)
        session.commit()
        session.refresh(enc)
        
        client_ip = request.client.host if request.client else "unknown"
        await log_audit_batched(
            actor=current_user.username, action="UPDATE_ENCOUNTER",
            resource_type="Encounter", resource_id=encounter_id,
            ip_address=client_ip, extra_metadata={"doctor_id": current_user.id}
        )
        return enc
