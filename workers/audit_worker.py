"""
Celery task to periodically flush audit logs from Redis to MongoDB
Runs every 5 seconds via Celery Beat
"""
from celery import shared_task
from app.services.audit_service import flush_audit_logs_sync
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def flush_audit_logs_task(self):
    """
    Periodic task to flush audit logs
    Runs every 5 seconds via Celery Beat schedule
    """
    try:
        flush_audit_logs_sync()
        return {"status": "success", "message": "Audit logs flushed"}
    except Exception as exc:
        logger.error(f"Audit flush task failed: {exc}")
        # Retry in 10 seconds
        raise self.retry(exc=exc, countdown=10)
