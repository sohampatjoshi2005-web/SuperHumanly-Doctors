import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlmodel import select
from app.db import get_session
from app.db_models import ExternalResource, SmartConnection

class FHIRSearchService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)

    async def fetch_resources(
        self, 
        iss: str, 
        token: str, 
        resource_type: str, 
        params: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Search for FHIR resources of a specific type.
        """
        url = f"{iss.rstrip('/')}/{resource_type}"
        headers = {
            "Accept": "application/fhir+json",
            "Authorization": f"Bearer {token}"
        }
        
        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        bundle = response.json()
        resources = []
        for entry in bundle.get("entry", []):
            if "resource" in entry:
                resources.append(entry["resource"])
        return resources

    async def sync_patient_context(
        self, 
        doctor_id: str, 
        patient_id: str, 
        iss: str,
        token: str
    ) -> Dict[str, int]:
        """
        Pull Medications, Observations, and Allergies for the patient.
        """
        resource_types = ["MedicationRequest", "Observation", "AllergyIntolerance"]
        counts = {}
        
        for r_type in resource_types:
            params = {"patient": patient_id}
            if r_type == "Observation":
                params["category"] = "laboratory,vital-signs"
            
            resources = await self.fetch_resources(iss, token, r_type, params)
            
            with get_session() as session:
                for res in resources:
                    fhir_id = res.get("id")
                    if not fhir_id:
                        continue
                        
                    # Deduplicate/Update
                    stmt = select(ExternalResource).where(
                        ExternalResource.doctor_id == doctor_id,
                        ExternalResource.fhir_id == fhir_id,
                        ExternalResource.resource_type == r_type
                    )
                    existing = session.exec(stmt).first()
                    
                    if existing:
                        existing.payload = res
                        existing.last_synced_at = datetime.utcnow()
                        session.add(existing)
                    else:
                        new_res = ExternalResource(
                            doctor_id=doctor_id,
                            patient_id=patient_id,
                            resource_type=r_type,
                            fhir_id=fhir_id,
                            payload=res
                        )
                        session.add(new_res)
                
                session.commit()
            counts[r_type] = len(resources)
            
        return counts

fhir_search_service = FHIRSearchService()
