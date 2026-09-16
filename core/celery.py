from celery import Celery
from app.core.config import settings
import os

from kombu import Queue

# Use Redis connection details from settings
redis_url = settings.redis_url

celery_app = Celery(
    "superhumanly_workers",
    broker=redis_url,
    backend=redis_url,
    include=[
        "app.workers.ai_tasks", 
        "app.workers.audit_worker",
        "app.workers.analytics_worker"
    ]
)

# Advanced Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600, # Increased to 1 hour for large audio batch processing
    
    # Reliability Settings
    task_acks_late=True,
    worker_prefetch_multiplier=1, # One task per worker to prevent blocking
    
    # Queue Definitions
    task_queues=(
        Queue("clinical.priority", routing_key="clinical.priority"),
        Queue("clinical.transcription", routing_key="clinical.transcription"),
        Queue("clinical.intelligence", routing_key="clinical.intelligence"),
        Queue("clinical.routine", routing_key="clinical.routine"),
        Queue("audit.batch", routing_key="audit.batch"),
    ),
    
    # Default Routing
    task_default_queue="clinical.routine",
    task_routes={
        "app.workers.audit_worker.*": {"queue": "audit.batch"},
        "app.workers.analytics_worker.*": {"queue": "clinical.routine"},
        "app.workers.ai_tasks.process_clinical_task": {"queue": "clinical.intelligence"},
    },

    # Periodic Tasks (Beat)
    beat_schedule={
        "flush-audit-logs-every-5s": {
            "task": "app.workers.audit_worker.flush_audit_logs_task",
            "schedule": 5.0,
        },
        "refresh-clinical-graphs-daily": {
            "task": "app.workers.analytics_worker.update_all_clinic_graphs_task",
            "schedule": 3600.0 * 24, # Every 24 hours
        },
    }
)

if __name__ == "__main__":
    celery_app.start()
