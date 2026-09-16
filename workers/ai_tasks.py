from celery import shared_task
import logging
import os
import time
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.langgraph.graph import build_graph
from app.services.rx_service import clean_transcript, extract_prescription
from app.services.formatting_service import format_prescription_text
from app.core.langgraph.tools.mailer import send_rx_email
from app.services.summary_service import generate_patient_summary
from app.services.billing_service import extract_billing_info
from app.services.storage_service import create_encounter, create_referral, create_followups
from app.db_models import Encounter, AuditLog
from app.core.config import settings

logger = logging.getLogger(__name__)

@shared_task(
    bind=True, 
    max_retries=5, 
    default_retry_delay=60, # 1 minute
    queue="clinical.routine"
)
def process_clinical_task(
    self, 
    data_type: str, # 'text' or 'audio'
    payload: Dict[str, Any],
    doctor_id: str,
    customer_id: Optional[str] = None,
    username: str = "unknown",
    clinic_id: Optional[str] = None
):
    """
    Main background task for processing clinical documentation.
    """
    start_time = datetime.utcnow()
    logger.info(f"🚀 Starting {data_type} processing task for doctor {doctor_id} in clinic {clinic_id}")
    try:
        from app.schemas.rx_schema import Prescription
        
        # Unified Analysis (1 LLM Call)
        transcript = ""
        audio_path = None
        language = None
        if data_type == "text":
            transcript = payload.get("transcript", "")
        else:
            audio_path = payload.get("audio_path")
            language = payload.get("language")
            
        # Fetch Patient History for context
        history_context = ""
        if customer_id:
            from app.db import get_session
            from sqlmodel import select
            with get_session() as session:
                # Fetch last 3 encounters for longitudinal context
                history_encounters = session.exec(
                    select(Encounter)
                    .where(Encounter.customer_id == customer_id)
                    .order_by(Encounter.created_at.desc())
                    .limit(3)
                ).all()
                
                if history_encounters:
                    history_context = "### PATIENT LONGITUDINAL HISTORY (Last 3 Encounters):\n"
                    for he in history_encounters:
                        date_str = he.created_at.strftime("%Y-%m-%d")
                        history_context += f"- Date: {date_str} | Diagnosis: {he.diagnosis or 'Unspecified'} | Summary: {he.patient_summary or 'None'}\n"
            logger.info(f"📜 Injected {len(history_encounters)} past encounters into context.")

        # Invoke the Parallelized LangGraph Swarm
        import asyncio
        initial_state = {
            "transcript": transcript,
            "audio_path": audio_path,
            "language": language,
            "historical_context": history_context,
            "to_email": payload.get("to_email"),
            "email_subject": payload.get("email_subject")
        }
        
        # Use existing graph instance
        from app.core.langgraph.graph import build_graph
        graph = build_graph()
        
        # Run graph with streaming updates
        final_state = initial_state.copy()
        
        from app.workers.clinical_progress import build_partial_result

        async def run_streaming_graph():
            nonlocal final_state
            logger.info("🧪 Starting LangGraph streaming execution...")
            segment_started = time.perf_counter()
            try:
                async for event in graph.astream(initial_state):
                    if not event or not isinstance(event, dict):
                        logger.warning(f"⚠️ Received non-dict event from graph: {event}")
                        continue

                    for node_name, state_update in event.items():
                        elapsed = time.perf_counter() - segment_started
                        logger.info(
                            f"✅ Node '{node_name}' completed stream segment. ⏱️ {elapsed:.2f}s"
                        )
                        segment_started = time.perf_counter()

                        if state_update and isinstance(state_update, dict):
                            final_state.update(state_update)
                            self.update_state(
                                state="PROGRESS",
                                meta={
                                    "current_node": node_name,
                                    "partial_result": build_partial_result(final_state),
                                },
                            )
            except Exception as stream_err:
                logger.error(f"❌ Error during graph streaming: {stream_err}")
                raise stream_err

            return final_state

        final_state = asyncio.run(run_streaming_graph())
        logger.info("✅ LangGraph clinical intelligence pipeline execution completed successfully.")
        
        # Map graph state to result structure
        rx = final_state.get("rx")
        billing = final_state.get("billing")
        soap = final_state.get("soap", {})
        
        result = {
            "transcript": transcript,
            "cleaned_text": final_state.get("cleaned_text"),
            "patient_summary": final_state.get("patient_summary"),
            "rx": rx,
            "rx_text": final_state.get("rx_text"),
            "billing": billing,
            "confidence_score": 0.98, # Fallback
            "email_status": final_state.get("email_status", "skipped"),
            "email_message_id": final_state.get("email_message_id"),
            "summary_sections": final_state.get("summary_sections"),
            "soap": soap,
            "referral_data": final_state.get("referral_data"),
            "wellness_data": final_state.get("wellness_data"),
            "rounds_report": final_state.get("rounds_report")
        }

        # Handle Email
        recipient = payload.get("to_email") or settings.email_default_to
        subject = payload.get("email_subject") or "Prescription Summary"
        email_status = result.get("email_status", "skipped")
        message_id = result.get("email_message_id")

        if data_type == "text" and settings.resend_api_key and recipient:
            try:
                message_id = send_rx_email(subject=subject, text_body=result["rx_text"], to_email=recipient)
                email_status = "sent"
            except Exception as e:
                logger.error(f"❌ Email sending failed: {e}")
                email_status = "failed"

        # Save to Database
        encounter_id = None
        
        # Helper to get values from dict or object
        def g(obj, key, default=None):
            if obj is None: return default
            if isinstance(obj, dict): return obj.get(key, default)
            return getattr(obj, key, default)

        if customer_id:
            from app.services.storage_service import get_customer

            customer = get_customer(customer_id)
            if not customer:
                raise ValueError(
                    f"Patient {customer_id} was not found. Select a valid patient in the registry."
                )
            if not clinic_id:
                clinic_id = customer.clinic_id

            # LOG AGENT START
            from app.services.audit_service import log_audit
            log_audit(
                actor="Lumina",
                action="ANALYZE",
                resource_type="encounter",
                resource_id="pending",
                extra_metadata={"status": "processing", "doctor_id": doctor_id, "clinic_id": clinic_id}
            )

            # Extract codes correctly
            billing_codes = g(billing, "codes", [])
            
            enc = Encounter(
                doctor_id=doctor_id,
                clinic_id=clinic_id,
                customer_id=customer_id,
                audio_filename=payload.get("audio_filename") if data_type == "audio" else None,
                transcript=result["transcript"],
                diagnosis=g(rx, "diagnosis"),
                patient_summary=result["patient_summary"],
                rx_json=rx.model_dump() if hasattr(rx, 'model_dump') else rx,
                rx_text=result["rx_text"],
                vitals_check=g(billing, "vitals_check"),
                complexity=g(billing, "complexity"),
                codes_reasoning=g(billing, "codes_reasoning"),
                codes_json={"codes": [c.model_dump() if hasattr(c, 'model_dump') else c for c in billing_codes]},
                email_to=recipient,
                email_subject=subject,
                email_status=email_status,
                email_message_id=message_id,
                clinical_data={
                    "risk_indicators": [r.model_dump() if hasattr(r, 'model_dump') else r for r in g(final_state.get("cds"), "risks", [])],
                    "summary_sections": result.get("summary_sections"),
                    "soap": result.get("soap")
                },
                rounds_report=result.get("rounds_report"),
                original_codes_json={"codes": [c.model_dump() if hasattr(c, 'model_dump') else c for c in billing_codes]},
                documentation_duration_sec=int((datetime.utcnow() - start_time).total_seconds()),
                confidence_score=g(rx, "confidence_score", 0.98)
            )
            saved_enc = create_encounter(enc)
            encounter_id = saved_enc.id

            if settings.clinical_async_verification:
                billing_snapshot = {}
                if isinstance(billing, dict):
                    billing_snapshot = {
                        "codes": billing.get("codes", []),
                        "complexity": billing.get("complexity"),
                        "vitals_check": billing.get("vitals_check"),
                    }
                verify_snapshot = {
                    "cleaned_text": final_state.get("cleaned_text") or result.get("transcript"),
                    "soap": result.get("soap") or {},
                    "billing": billing_snapshot,
                }
                verify_encounter_async.apply_async(
                    kwargs={"encounter_id": encounter_id, "snapshot": verify_snapshot},
                    queue="clinical.routine",
                )
                logger.info(f"🔍 Queued async QA verification for encounter {encounter_id}")

            # CREATE REFERRAL IF DETECTED
            referral_data = result.get("referral_data")
            if referral_data:
                from app.db_models import Referral
                referral = Referral(
                    encounter_id=encounter_id,
                    doctor_id=doctor_id,
                    patient_id=customer_id,
                    specialty=referral_data.get("specialty"),
                    reason=referral_data.get("reason"),
                    priority=referral_data.get("priority"),
                    letter_text=referral_data.get("letter_text"),
                    insurance_notes=referral_data.get("insurance_notes"),
                    status="Draft"
                )
                create_referral(referral)
                logger.info(f"📄 AI Referral Draft created for encounter {encounter_id}")

            # CREATE FOLLOWUPS IF DETECTED
            wellness_data = result.get("wellness_data")
            if wellness_data and "followups" in wellness_data:
                from app.db_models import PatientFollowup
                followups = []
                for f in wellness_data["followups"]:
                    followup = PatientFollowup(
                        encounter_id=encounter_id,
                        doctor_id=doctor_id,
                        patient_id=customer_id,
                        instruction=f.get("instruction"),
                        due_date=datetime.fromisoformat(f.get("due_date")) if isinstance(f.get("due_date"), str) else f.get("due_date"),
                        status="Pending"
                    )
                    followups.append(followup)
                
                create_followups(followups)
                logger.info(f"🧘 {len(wellness_data['followups'])} AI Follow-ups created for encounter {encounter_id}")

            # LOG AGENT SUCCESS
            log_audit(
                actor="Atlas",
                action="SYNC",
                resource_type="encounter",
                resource_id=encounter_id,
                extra_metadata={"status": "completed", "doctor_id": doctor_id, "clinic_id": clinic_id}
            )

        # Cleanup audio file if it exists
        if data_type == "audio" and os.path.exists(payload.get("audio_path")):
            try:
                os.remove(payload.get("audio_path"))
                logger.info(f"🧹 Cleaned up temp file: {payload.get('audio_path')}")
            except:
                pass

        return {
            "encounter_id": encounter_id,
            "transcript": result["transcript"],
            "cleaned_text": result["cleaned_text"],
            "patient_summary": result["patient_summary"],
            "summary_sections": result.get("summary_sections"),
            "soap": result.get("soap"),
            "rx": rx.model_dump() if hasattr(rx, 'model_dump') else rx,
            "rx_text": result["rx_text"],
            "rx_summary": result["rx_text"], # ALIGN WITH FRONTEND
            "vitals_check": g(billing, "vitals_check"),
            "complexity": g(billing, "complexity"),
            "codes_reasoning": g(billing, "codes_reasoning"),
            "billing_codes": [c.model_dump() if hasattr(c, 'model_dump') else c for c in g(billing, "codes", [])],
            "diagnosis": g(rx, "diagnosis"),
            "medicines": [m.model_dump() if hasattr(m, 'model_dump') else m for m in g(rx, "medicines", [])],
            "advice": g(rx, "advice"),
            "follow_up": g(rx, "follow_up"),
            "risk_indicators": [r.model_dump() if hasattr(r, 'model_dump') else r for r in g(final_state.get("cds"), "risks", [])],
            "rounds_report": result.get("rounds_report"),
            "referral_data": result.get("referral_data"),
            "wellness_data": result.get("wellness_data"),
            "email_status": email_status,
            "email_message_id": message_id,
            "confidence_score": g(rx, "confidence_score", 0.98)
        }

    except Exception as e:
        logger.error(f"❌ Clinical task failed: {e}")
        err = str(e).lower()
        if "foreign key" in err or ("patient" in err and "not found" in err):
            raise
        if "429" in str(e) or "Resource Exhausted" in str(e):
            logger.info("⏳ Quota exhausted. Retrying with exponential backoff...")
            raise self.retry(exc=e, countdown=2 ** self.request.retries * 10)
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, queue="clinical.routine", max_retries=2, default_retry_delay=30)
def verify_encounter_async(self, encounter_id: str, snapshot: Dict[str, Any]):
    """
    Background QA pass: patches encounter SOAP/billing after the UI has results.
  """
    import asyncio
    from app.core.langgraph.nodes.verification import verification_node
    from app.services.storage_service import patch_encounter_clinical

    try:
        state = {
            "cleaned_text": snapshot.get("cleaned_text", ""),
            "soap": snapshot.get("soap") or {},
            "billing": snapshot.get("billing") or {},
        }
        corrections = asyncio.run(verification_node(state))
        if not corrections:
            return {"encounter_id": encounter_id, "status": "no_changes"}

        patch_encounter_clinical(
            encounter_id,
            soap=corrections.get("soap"),
            billing=corrections.get("billing"),
            audit_logs=corrections.get("verification_audit"),
        )
        logger.info(f"✅ Async verification applied for encounter {encounter_id}")
        return {"encounter_id": encounter_id, "status": "patched"}
    except Exception as exc:
        logger.error(f"❌ Async verification failed for {encounter_id}: {exc}")
        raise self.retry(exc=exc)
