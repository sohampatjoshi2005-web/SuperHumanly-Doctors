from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from sqlmodel import select
from app.api.v1.auth import get_current_user
from app.db_models import User, SmartConnection
from app.db import get_session
from app.services.smart_auth_service import smart_auth_service
from app.core.config import settings

router = APIRouter(prefix="/auth/smart", tags=["smart-auth"])

@router.get("/launch")
async def smart_launch(
    request: Request,
    iss: str = Query(..., description="FHIR Server URL"),
    launch: Optional[str] = Query(None, description="EHR Launch context handle"),
    current_user: User = Depends(get_current_user)
):
    """
    Step 1: Initiate SMART on FHIR launch.
    """
    # Define redirect URI - must match EHR registration
    redirect_uri = f"{request.base_url.rstrip('/')}{settings.smart_callback_path}"
    
    # In a real app, client_id and scopes would be stored per EHR system
    client_id = settings.smart_client_id
    scope = settings.smart_scope
    
    try:
        auth_context = await smart_auth_service.get_authorization_url(
            iss=iss,
            redirect_uri=redirect_uri,
            client_id=client_id,
            scope=scope,
            launch=launch
        )
        
        # Store context in session for callback verification
        request.session["smart_state"] = auth_context["state"]
        request.session["smart_code_verifier"] = auth_context["code_verifier"]
        request.session["smart_iss"] = iss
        
        return RedirectResponse(url=auth_context["auth_url"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SMART launch failed: {str(e)}")

@router.get("/callback")
async def smart_callback(
    request: Request,
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    current_user: User = Depends(get_current_user)
):
    """
    Step 2: Handle SMART on FHIR callback.
    """
    # 1. Verify state
    saved_state = request.session.get("smart_state")
    if not saved_state or state != saved_state:
        raise HTTPException(status_code=403, detail="Invalid state parameter")
    
    code_verifier = request.session.get("smart_code_verifier")
    iss = request.session.get("smart_iss")
    
    if not code_verifier or not iss:
        raise HTTPException(status_code=400, detail="Missing session context")

    # 2. Exchange code for token
    redirect_uri = f"{request.base_url.rstrip('/')}{settings.smart_callback_path}"
    client_id = settings.smart_client_id
    
    try:
        token_data = await smart_auth_service.exchange_code_for_token(
            iss=iss,
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            client_id=client_id
        )
        
        # 3. Save to database
        with get_session() as session:
            # Check for existing connection for this doctor/iss
            stmt = select(SmartConnection).where(
                SmartConnection.doctor_id == current_user.id,
                SmartConnection.fhir_iss == iss
            )
            existing = session.exec(stmt).first()
            
            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            if existing:
                existing.access_token = token_data["access_token"]
                existing.refresh_token = token_data.get("refresh_token")
                existing.expires_at = expires_at
                existing.patient_context_id = token_data.get("patient")
                session.add(existing)
            else:
                conn = SmartConnection(
                    doctor_id=current_user.id,
                    clinic_id=current_user.clinic_id,
                    fhir_iss=iss,
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token"),
                    expires_at=expires_at,
                    patient_context_id=token_data.get("patient")
                )
                session.add(conn)
            
            session.commit()
            
        # Clear session
        request.session.pop("smart_state", None)
        request.session.pop("smart_code_verifier", None)
        
        return {"status": "success", "message": "SMART connection established", "patient_id": token_data.get("patient")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {str(e)}")

@router.get("/status")
async def smart_status(current_user: User = Depends(get_current_user)):
    """
    Check current SMART connection status.
    """
    with get_session() as session:
        stmt = select(SmartConnection).where(SmartConnection.doctor_id == current_user.id)
        conns = session.exec(stmt).all()
        return [
            {
                "fhir_iss": c.fhir_iss,
                "patient_id": c.patient_context_id,
                "expires_at": c.expires_at,
                "is_active": c.expires_at > datetime.utcnow()
            }
            for c in conns
        ]
