from celery import shared_task
from app.services.clinical_graph_service import ClinicalGraphService
from app.db import get_session
from app.db_models import Clinic
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

@shared_task
def update_all_clinic_graphs_task():
    """
    Daily task to refresh clinical graphs for all active clinics.
    Ensures the Graph Intelligence Portal stays up to date.
    """
    logger.info("🕸️ Starting Daily Clinical Graph Refresh Swarm")
    
    try:
        with get_session() as session:
            clinics = session.exec(select(Clinic).where(Clinic.is_active == True)).all()
            
            for clinic in clinics:
                logger.info(f"📊 Refreshing graph for clinic: {clinic.name} ({clinic.id})")
                # ClinicalGraphService.build_clinic_graph already does the work.
                # In a real system, we'd cache this in Redis.
                ClinicalGraphService.get_clinical_insights(str(clinic.id))
                
        logger.info("✅ Clinical Graph Refresh Swarm Completed")
        return {"status": "success", "clinics_processed": len(clinics)}
    except Exception as e:
        logger.error(f"❌ Clinical Graph Refresh failed: {e}")
        return {"status": "error", "message": str(e)}
