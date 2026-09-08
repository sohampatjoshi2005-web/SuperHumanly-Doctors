from typing import Optional
import os
from uuid import uuid4
from tempfile import NamedTemporaryFile
from starlette.concurrency import run_in_threadpool

from app.api.v1.auth import get_current_user
from app.db_models import User
from fastapi import APIRouter, UploadFile, File, Form, Depends

from app.core.langgraph.graph import build_graph

from app.api.v1.customers import require_customer_access
from app.api.v1.dependencies import check_trial_status
from app.services.meter_service import increment_usage
from app.db import get_async_session, get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db_models import AuditLog, Encounter
from fastapi import Request
from app.services.storage_service import create_encounter

router = APIRouter(prefix="/process-audio", tags=["process"])

graph = build_graph()


@router.post("")
async def process_audio(
    request: Request,
    audio: UploadFile = File(...),
    customer_id: Optional[str] = Form(default=None),
    to_email: Optional[str] = Form(default=None),
    email_subject: Optional[str] = Form(default=None),
    language: Optional[str] = Form(default=None),
    priority: bool = Form(default=False),
    current_user: User = Depends(get_current_user),
    _ = Depends(check_trial_status)
):
    from app.core.config import settings
    from fastapi import HTTPException

    if not customer_id:
        raise HTTPException(
            status_code=400,
            detail="A patient must be selected before processing audio.",
        )
    patient = require_customer_access(customer_id, current_user)
    clinic_id = current_user.clinic_id or patient.clinic_id

    # Ensure shared volume directory exists
    os.makedirs(settings.shared_storage_dir, exist_ok=True)
    
    # Save file to shared volume
    tmp_path = f"{settings.shared_storage_dir.rstrip('/')}/{uuid4()}_{audio.filename}"
    with open(tmp_path, "wb") as buffer:
        buffer.write(await audio.read())

    from app.workers.ai_tasks import process_clinical_task
    
    # Submit task to Celery
    queue = "clinical.priority" if priority else "clinical.transcription"
    task = process_clinical_task.apply_async(
        kwargs={
            "data_type": "audio",
            "payload": {
                "audio_path": tmp_path,
                "audio_filename": audio.filename,
                "to_email": to_email,
                "email_subject": email_subject,
                "language": language
            },
            "doctor_id": str(current_user.id),
            "customer_id": customer_id,
            "username": current_user.username,
            "clinic_id": clinic_id
        },
        queue=queue
    )

    # Increment usage count immediately
    async for session in get_async_session():
        await increment_usage(str(current_user.id), session)

    # Log Audit
    client_ip = request.client.host if request.client else "unknown"
    audit = AuditLog(
        actor=current_user.username,
        action="GENERATE_TRANSCRIPT_ASYNC",
        resource_type="Audio",
        resource_id=task.id,
        ip_address=client_ip
    )
    with get_session() as session:
        session.add(audit)
        session.commit()

    return {
        "task_id": task.id,
        "status": "PENDING",
        "message": "Audio transcription and analysis started in background."
    }
