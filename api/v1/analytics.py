from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.api.v1.auth import get_current_user, get_current_admin
from app.db_models import User
from app.services.clinical_graph_service import ClinicalGraphService

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/graph")
async def get_clinic_graph(current_user: User = Depends(get_current_user)):
    """
    Returns the clinical knowledge graph for the user's clinic.
    """
    if not current_user.clinic_id:
        raise HTTPException(status_code=400, detail="User is not associated with a clinic")
    
    return ClinicalGraphService.build_clinic_graph(str(current_user.clinic_id))

@router.get("/insights")
async def get_clinic_insights(current_user: User = Depends(get_current_user)):
    """
    Returns high-level graph insights and clusters for the clinic.
    """
    if not current_user.clinic_id:
        raise HTTPException(status_code=400, detail="User is not associated with a clinic")
    
    return ClinicalGraphService.get_clinical_insights(str(current_user.clinic_id))

@router.get("/admin/clinic/{clinic_id}/graph")
async def admin_get_clinic_graph(clinic_id: str, current_admin: User = Depends(get_current_admin)):
    """
    Admin-only: Returns the graph for any specific clinic.
    """
    return ClinicalGraphService.build_clinic_graph(clinic_id)
