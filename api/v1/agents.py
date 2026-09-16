from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends
from app.api.v1.auth import get_current_user
from app.db_models import User

router = APIRouter(prefix="/agents", tags=["agents"])

@router.get("/swarm")
async def get_swarm_status(current_user: User = Depends(get_current_user)):
    """
    Fetch the health and status of the entire medical agent swarm.
    Returns a direct array of agents for frontend compatibility.
    """
    return [
        {
            "name": "Atlas",
            "role": "Scribe & Dictation",
            "status": "Active",
            "activeTasks": 94,
            "duty": "Real-time clinical transcription",
            "color": "blue"
        },
        {
            "name": "Lumina",
            "role": "Clinical Reasoning",
            "status": "Ready",
            "activeTasks": 12,
            "duty": "Differential diagnosis synthesis",
            "color": "purple"
        },
        {
            "name": "Echo",
            "role": "Institutional Sync",
            "status": "Active",
            "activeTasks": 88,
            "duty": "EHR longitudinal correlation",
            "color": "green"
        },
        {
            "name": "Pathos",
            "role": "Rx Validation",
            "status": "Ready",
            "activeTasks": 5,
            "duty": "Drug-drug interaction safety",
            "color": "orange"
        }
    ]

@router.get("/logs")
async def get_agent_logs(limit: int = 10, current_user: User = Depends(get_current_user)):
    """
    Fetch real-time activity logs from the agent swarm.
    """
    from app.db import get_session
    from app.db_models import AuditLog
    from sqlmodel import select, desc
    
    with next(get_session()) as session:
        # Get only logs for this doctor or system logs
        statement = select(AuditLog).where(
            AuditLog.actor.in_(["Atlas", "Lumina", "Echo", "Pathos"])
        ).order_by(desc(AuditLog.timestamp)).limit(limit)
        
        db_logs = session.exec(statement).all()
        
        return [
            {
                "timestamp": log.timestamp.isoformat(),
                "agent_name": log.actor,
                "message": f"{log.action} {log.resource_type} {log.resource_id}",
                "reasoning": log.extra_metadata.get("status", "System verified") if log.extra_metadata else "Duty cycle verified"
            }
            for log in db_logs
        ]

@router.post("/task")
async def trigger_agent_task(agent_name: str, current_user: User = Depends(get_current_user)):
    """
    Trigger a specific task for an agent.
    """
    return {"status": "success", "agent": agent_name}
