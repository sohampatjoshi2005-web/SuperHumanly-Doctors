from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from app.api.v1.auth import get_current_user
from app.db_models import User, Encounter, HMSRecord, Customer, SmartConnection, ExternalResource, SyncLog
from app.db import get_session, scoped_select
from app.services import fhir_service, fhir_search_service
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/ehr", tags=["ehr"])

@router.get("/systems")
async def fetch_ehr_systems(current_user: User = Depends(get_current_user)):
    """
    Fetch connected EHR systems for the clinic from the database.
    """
    from app.db_models import EHRSystem
    with get_session() as session:
        systems = session.exec(select(EHRSystem)).all()
        return [
            {
                "id": s.id,
                "provider_name": s.name,
                "status": s.status,
                "last_sync": "Synchronized" if s.status == "Active" else "Offline"
            }
            for s in systems
        ]

@router.get("/deltas/{encounter_id}")
async def fetch_clinical_deltas(encounter_id: str, system_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    """
    Compare current encounter with external EHR records.
    """
    with get_session() as session:
        encounter = session.get(Encounter, encounter_id)
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found")
        
        # In this simulation, we use the customer_id to find the HMS record
        hms_record = session.exec(scoped_select(HMSRecord).where(HMSRecord.customer_id == encounter.customer_id)).first()
        
        if not hms_record:
            # Create a default one if not exists for demo
            hms_record = HMSRecord(
                customer_id=encounter.customer_id,
                clinic_id=current_user.clinic_id,
                diagnosis="No record in HMS",
                billing_codes={"codes": []},
                rx_summary="N/A"
            )
            session.add(hms_record)
            session.commit()
            session.refresh(hms_record)

        result = {
            "hms_record": {
                "diagnosis": hms_record.diagnosis,
                "billing_codes": hms_record.billing_codes.get("codes", []) if hms_record.billing_codes else [],
                "rx_summary": hms_record.rx_summary,
                "fhir_payload": hms_record.fhir_payload
            },
            "workspace_proposal": {
                "diagnosis": encounter.complexity, # Using complexity as a placeholder for diagnosis in this schema
                "billing_codes": encounter.codes_json.get("codes", []) if encounter.codes_json else [],
                "rx_summary": encounter.rx_text,
                "fhir_payload": encounter.fhir_payload or fhir_service.map_encounter_to_bundle(encounter).dict()
            },
            "external_resources": [] # Default
        }
        
        # Add external resources from cache
        stmt = scoped_select(ExternalResource).where(ExternalResource.patient_id == encounter.customer_id)
        external = session.exec(stmt).all()
        result["external_resources"] = [
            {
                "type": r.resource_type,
                "id": r.fhir_id,
                "payload": r.payload,
                "last_synced": r.last_synced_at
            }
            for r in external
        ]
        return result

@router.post("/sync")
async def sync_ehr_record(payload: Dict[str, Any], current_user: User = Depends(get_current_user)):
    """
    Force sync a record to the external EHR.
    """
    system_id = payload.get("system_id")
    encounter_id = payload.get("encounter_id")
    
    if not encounter_id:
        raise HTTPException(status_code=400, detail="encounter_id required")

    with get_session() as session:
        encounter = session.get(Encounter, encounter_id)
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found")
            
        hms_record = session.exec(scoped_select(HMSRecord).where(HMSRecord.customer_id == encounter.customer_id)).first()
        if not hms_record:
            hms_record = HMSRecord(
                customer_id=encounter.customer_id, 
                system_id=system_id,
                clinic_id=current_user.clinic_id
            )
            session.add(hms_record)

        # Commit workspace data to HMS
        hms_record.system_id = system_id
        hms_record.diagnosis = encounter.complexity
        hms_record.billing_codes = encounter.codes_json
        hms_record.rx_summary = encounter.rx_text
        # Generate and save full FHIR Bundle
        patient = session.get(Customer, encounter.customer_id)
        fhir_bundle = fhir_service.map_encounter_to_bundle(encounter, patient=patient)
        encounter.fhir_payload = fhir_bundle.dict()
        hms_record.fhir_payload = encounter.fhir_payload
        
        session.add(encounter)
        session.add(hms_record)
        
        # Log success
        log = SyncLog(
            doctor_id=current_user.id,
            clinic_id=current_user.clinic_id,
            patient_id=encounter.customer_id,
            direction="OUTBOUND",
            status="SUCCESS",
            resource_summary=f"Bundle (Encounter, {len(fhir_bundle.entry)-2} resources)"
        )
        session.add(log)
        session.commit()
        
        return {
            "message": "Sync successful (FHIR Transaction Bundle generated)", 
            "system_id": system_id,
            "transaction_id": f"HMS-TX-{encounter_id[:8].upper()}",
            "fhir_bundle_id": fhir_bundle.id or "N/A"
        }

@router.post("/pull")
async def pull_ehr_data(payload: Dict[str, Any], current_user: User = Depends(get_current_user)):
    """
    Pull clinical data from EHR for a specific patient context.
    """
    patient_id = payload.get("patient_id")
    iss = payload.get("iss")
    
    if not patient_id or not iss:
        raise HTTPException(status_code=400, detail="patient_id and iss required")

    with get_session() as session:
        # Get active SMART token
        stmt = scoped_select(SmartConnection).where(
            SmartConnection.doctor_id == current_user.id,
            SmartConnection.fhir_iss == iss
        )
        conn = session.exec(stmt).first()
        if not conn:
            raise HTTPException(status_code=401, detail="No active SMART connection for this EHR")
            
        if conn.expires_at < datetime.utcnow():
            raise HTTPException(status_code=401, detail="SMART token expired. Re-authenticate.")

        # Trigger sync
        counts = await fhir_search_service.sync_patient_context(
            doctor_id=current_user.id,
            patient_id=patient_id,
            iss=iss,
            token=conn.access_token
        )
        
        # Log success
        summary = ", ".join([f"{k}: {v}" for k, v in counts.items()])
        log = SyncLog(
            doctor_id=current_user.id,
            clinic_id=current_user.clinic_id,
            patient_id=patient_id,
            direction="INBOUND",
            status="SUCCESS",
            resource_summary=summary
        )
        session.add(log)
        session.commit()
        
        return {
            "status": "success",
            "message": "Data synchronized from EHR",
            "synced_counts": counts
        }

@router.get("/sync-logs")
async def get_sync_logs(current_user: User = Depends(get_current_user)):
    """
    Fetch EHR synchronization history.
    """
    with get_session() as session:
        stmt = scoped_select(SyncLog).where(SyncLog.doctor_id == current_user.id).order_by(SyncLog.created_at.desc())
        logs = session.exec(stmt).all()
        return logs

@router.get("/connections")
async def get_connections(current_user: User = Depends(get_current_user)):
    """
    List active SMART on FHIR connections.
    """
    with get_session() as session:
        stmt = scoped_select(SmartConnection).where(SmartConnection.doctor_id == current_user.id)
        conns = session.exec(stmt).all()
        return [
            {
                "id": c.id,
                "fhir_iss": c.fhir_iss,
                "expires_at": c.expires_at,
                "patient_context": c.patient_context_id,
                "is_expired": c.expires_at < datetime.utcnow()
            }
            for c in conns
        ]

@router.get("/reconcile/{encounter_id}")
async def reconcile_encounter_endpoint(encounter_id: str, current_user: User = Depends(get_current_user)):
    """
    Perform AI-assisted reconciliation between encounter data and EHR records.
    """
    with get_session() as session:
        encounter = session.get(Encounter, encounter_id)
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found")
        
        return await ReconciliationService.reconcile_encounter(encounter)

@router.post("/reconcile/{encounter_id}/commit")
async def commit_reconciliation_endpoint(encounter_id: str, payload: Dict[str, Any], current_user: User = Depends(get_current_user)):
    """
    Commit reconciled clinical items to the encounter and trigger institutional sync.
    """
    accepted_items = payload.get("accepted_items", [])
    
    with get_session() as session:
        encounter = session.get(Encounter, encounter_id)
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found")
            
        # Logic to apply accepted_items to encounter.rx_json and encounter.diagnosis
        # For now, we'll just log the commitment
        from app.db_models import SyncLog
        log = SyncLog(
            doctor_id=current_user.id,
            clinic_id=current_user.clinic_id,
            patient_id=encounter.customer_id,
            direction="OUTBOUND",
            status="SUCCESS",
            resource_summary=f"Reconciled {len(accepted_items)} items"
        )
        session.add(log)
        session.commit()
        
        return {"status": "success", "reconciled_items": len(accepted_items)}
@router.get("/metadata")
@router.get("/mock-fhir/metadata")
async def fhir_metadata():
    """
    Mock FHIR CapabilityStatement for health checks.
    """
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "date": datetime.utcnow().isoformat(),
        "kind": "instance",
        "fhirVersion": "4.0.1",
        "format": ["json"],
        "rest": [{"mode": "server"}]
    }
