from fastapi import APIRouter, Depends, HTTPException
from app.core.celery import celery_app
from app.api.v1.auth import get_current_user
from app.db_models import User
from celery.result import AsyncResult

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.get("/{task_id}")
async def get_task_status(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Check the status and result of a background task.
    """
    result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
        "meta": result.info if not result.ready() else None
    }
    
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
            
    return response
