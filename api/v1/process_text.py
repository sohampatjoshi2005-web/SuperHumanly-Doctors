from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from app.core.langgraph.graph import build_graph
from app.services.rx_service import clean_transcript
from app.services.rx_service import extract_prescription
from app.services.formatting_service import format_prescription_text
from app.core.langgraph.tools.mailer import send_rx_email
from app.services.summary_service import generate_patient_summary
from app.core.config import settings

from app.api.v1.auth import get_current_user
from app.db_models import User
from fastapi import APIRouter, Depends

from app.api.v1.customers import require_customer_access
from app.api.v1.dependencies import check_trial_status
from fastapi import HTTPException
from app.services.meter_service import increment_usage
from app.db import get_async_session, get_session
from app.db_models import AuditLog, Encounter
from fastapi import Request

from app.services.billing_service import extract_billing_info
from app.services.storage_service import create_encounter

router = APIRouter(prefix="/process-text", tags=["process"])

graph = build_graph()


class TextRequest(BaseModel):
    transcript: str
    customer_id: Optional[str] = None
    to_email: Optional[str] = None
    email_subject: Optional[str] = None
    priority: bool = False


@router.post("")
async def process_text(
    request: Request,
    payload: TextRequest, 
    current_user: User = Depends(get_current_user),
    _ = Depends(check_trial_status)
):
    from app.workers.ai_tasks import process_clinical_task

    if not payload.customer_id:
        raise HTTPException(
            status_code=400,
            detail="A patient must be selected before processing clinical text.",
        )
    patient = require_customer_access(payload.customer_id, current_user)
    clinic_id = current_user.clinic_id or patient.clinic_id

    # Submit task to Celery
    queue = "clinical.priority" if payload.priority else "clinical.intelligence"
    task = process_clinical_task.apply_async(
        kwargs={
            "data_type": "text",
            "payload": payload.model_dump(),
            "doctor_id": str(current_user.id),
            "customer_id": payload.customer_id,
            "username": current_user.username,
            "clinic_id": clinic_id
        },
        queue=queue
    )

    # Increment usage count immediately (gating policy)
    async for session in get_async_session():
        await increment_usage(str(current_user.id), session)

    # Log Audit
    client_ip = request.client.host if request.client else "unknown"
    audit = AuditLog(
        actor=current_user.username,
        action="GENERATE_TRANSCRIPT_ASYNC",
        resource_type="Text",
        resource_id=task.id,
        ip_address=client_ip
    )
    with get_session() as session:
        session.add(audit)
        session.commit()

    return {
        "task_id": task.id,
        "status": "PENDING",
        "message": "Clinical analysis started in background."
    }
