from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from app.api.v1.auth import get_current_user
from app.db_models import User, Referral, Encounter
from app.db import get_session, scoped_select

router = APIRouter(prefix="/referrals", tags=["referrals"])

@router.get("/encounter/{encounter_id}", response_model=List[Referral])
async def get_referrals_by_encounter(encounter_id: str, current_user: User = Depends(get_current_user)):
    """
    Fetch all referrals associated with a specific encounter.
    """
    with get_session() as session:
        stmt = scoped_select(Referral).where(Referral.encounter_id == encounter_id)
        referrals = session.exec(stmt).all()
        return referrals

@router.get("/{referral_id}", response_model=Referral)
async def get_referral(referral_id: str, current_user: User = Depends(get_current_user)):
    """
    Fetch a single referral by ID.
    """
    with get_session() as session:
        referral = session.get(Referral, referral_id)
        if not referral:
            raise HTTPException(status_code=404, detail="Referral not found")
        return referral

@router.post("/{referral_id}/finalize")
async def finalize_referral(referral_id: str, current_user: User = Depends(get_current_user)):
    """
    Mark a referral as finalized/sent.
    """
    with get_session() as session:
        referral = session.get(Referral, referral_id)
        if not referral:
            raise HTTPException(status_code=404, detail="Referral not found")
        
        referral.status = "Sent"
        session.add(referral)
        session.commit()
        session.refresh(referral)
        return referral
