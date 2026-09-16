from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from app.db_models import TrialRequest
from app.db import get_session
from sqlmodel import select
from datetime import datetime

router = APIRouter(prefix="/trial", tags=["trial"])

class TrialCreate(BaseModel):
    full_name: str
    email: EmailStr
    institution: str
    professional_role: str
    use_case: str

@router.post("/request", status_code=status.HTTP_201_CREATED)
async def request_trial(trial_in: TrialCreate):
    with get_session() as session:
        # Check if request already exists for this email
        existing = session.exec(select(TrialRequest).where(TrialRequest.email == trial_in.email)).first()
        if existing:
            raise HTTPException(
                status_code=400, 
                detail="A trial request with this email is already being processed."
            )
        
        trial = TrialRequest(**trial_in.dict())
        session.add(trial)
        session.commit()
        
    return {"status": "success", "message": "Trial request transmitted to Medical Engineering."}
