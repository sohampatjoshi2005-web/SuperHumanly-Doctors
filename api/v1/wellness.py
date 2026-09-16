from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from app.api.v1.auth import get_current_user
from app.db_models import User, PatientFollowup, AdherenceLog
from app.db import get_session, scoped_select

router = APIRouter(prefix="/wellness", tags=["wellness"])

@router.get("/patient/{patient_id}/followups", response_model=List[PatientFollowup])
async def get_patient_followups(patient_id: str, current_user: User = Depends(get_current_user)):
    """
    Fetch all follow-up instructions for a specific patient.
    """
    with get_session() as session:
        stmt = scoped_select(PatientFollowup).where(PatientFollowup.patient_id == patient_id)
        followups = session.exec(stmt).all()
        return followups

@router.post("/adherence/log")
async def log_adherence(log: AdherenceLog, current_user: User = Depends(get_current_user)):
    """
    Log a medication adherence event (Taken/Missed).
    """
    with get_session() as session:
        session.add(log)
        session.commit()
        session.refresh(log)
        return log

@router.get("/patient/{patient_id}/score")
async def get_adherence_score(patient_id: str, current_user: User = Depends(get_current_user)):
    """
    Calculate the adherence score for a patient based on logs.
    """
    with get_session() as session:
        stmt = select(AdherenceLog).where(AdherenceLog.patient_id == patient_id)
        logs = session.exec(stmt).all()
        if not logs:
            return {"score": 1.0, "total_logs": 0}
            
        taken = sum(1 for l in logs if l.taken_status)
        return {
            "score": taken / len(logs),
            "total_logs": len(logs),
            "taken": taken,
            "missed": len(logs) - taken
        }
