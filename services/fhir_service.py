from typing import Dict, Any, Optional, List
from fhir.resources.patient import Patient
from fhir.resources.encounter import Encounter as FHIREncounter
from fhir.resources.identifier import Identifier
from fhir.resources.humanname import HumanName
from fhir.resources.coding import Coding
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.condition import Condition
from fhir.resources.medicationrequest import MedicationRequest
from fhir.resources.documentreference import DocumentReference
from fhir.resources.flag import Flag
from fhir.resources.bundle import Bundle, BundleEntry, BundleEntryRequest
import base64
import uuid
from app.db_models import Customer, Encounter

def map_customer_to_patient(customer: Customer) -> Patient:
    """
    Converts a Superhumanly Customer to a FHIR R4 Patient resource.
    """
    name_parts = (customer.name or "Unknown Patient").split(" ", 1)
    family = name_parts[1] if len(name_parts) > 1 else name_parts[0]
    given = [name_parts[0]] if len(name_parts) > 1 else [""]
    
    patient_dict = {
        "resourceType": "Patient",
        "id": customer.id,
        "active": True,
        "name": [
            {
                "family": family,
                "given": given,
                "use": "official"
            }
        ],
        "identifier": [
            {
                "system": "http://superhumanlydoctors.io/patient-id",
                "value": customer.id
            }
        ]
    }
    
    return Patient.parse_obj(patient_dict)

def map_encounter_to_fhir(encounter: Encounter, patient: Optional[Customer] = None) -> FHIREncounter:
    """
    Converts a Superhumanly Encounter to a FHIR R4 Encounter resource.
    Note: Adjusted for fhir.resources 7.1.0 specific field aliases.
    """
    status = "finished" 
    
    encounter_dict = {
        "resourceType": "Encounter",
        "id": encounter.id,
        "status": status,
        "class": [ 
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                        "code": "AMB",
                        "display": "ambulatory"
                    }
                ]
            }
        ],
        "subject": {
            "reference": f"Patient/{encounter.customer_id}",
            "display": patient.name if patient else "Unknown Patient"
        },
        "reason": [] 
    }
    
    # Map complexity
    if encounter.complexity:
        encounter_dict["reason"].append({
            "value": [
                {
                    "concept": {
                        "text": f"Clinical Complexity: {encounter.complexity}"
                    }
                }
            ]
        })
        
    # Map billing codes
    if encounter.codes_json and "codes" in encounter.codes_json:
        for code_entry in encounter.codes_json["codes"]:
            code_val = code_entry if isinstance(code_entry, str) else code_entry.get("code", "N/A")
            encounter_dict["reason"].append({
                "value": [
                    {
                        "concept": {
                            "coding": [
                                {
                                    "system": "http://hl7.org/fhir/sid/icd-10",
                                    "code": code_val
                                }
                            ]
                        }
                    }
                ]
            })

    return FHIREncounter.parse_obj(encounter_dict)

def validate_fhir_resource(resource_dict: Dict[str, Any], resource_type: str) -> bool:
    """
    Validates a dictionary against a specific FHIR resource type.
    """
    try:
        if resource_type == "Patient":
            Patient.parse_obj(resource_dict)
        elif resource_type == "Encounter":
            FHIREncounter.parse_obj(resource_dict)
        else:
            return False
        return True
    except Exception:
        return False

def map_to_condition(encounter: Encounter) -> List[Condition]:
    """
    Extracts diagnoses from an encounter and returns a list of FHIR Condition resources.
    """
    conditions = []
    if encounter.codes_json and "codes" in encounter.codes_json:
        for code_entry in encounter.codes_json["codes"]:
            code_val = code_entry if isinstance(code_entry, str) else code_entry.get("code", "N/A")
            display = code_entry if isinstance(code_entry, str) else code_entry.get("display", code_val)
            
            condition_dict = {
                "resourceType": "Condition",
                "id": str(uuid.uuid4()),
                "clinicalStatus": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]
                },
                "verificationStatus": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]
                },
                "category": [
                    {
                        "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category", "code": "encounter-diagnosis"}]
                    }
                ],
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": code_val, "display": display}],
                    "text": display
                },
                "subject": {"reference": f"Patient/{encounter.customer_id}"}
            }
            conditions.append(Condition.parse_obj(condition_dict))
    return conditions

def map_to_medication_request(encounter: Encounter) -> List[MedicationRequest]:
    """
    Extracts prescriptions from an encounter and returns a list of FHIR MedicationRequest resources.
    """
    requests = []
    # Simplified: extracting from rx_text if structured rx_json is missing
    # In a real app, this would use the structured prescription data
    if encounter.rx_text:
        # For demo, we treat the whole rx_text as one request if it looks like a drug
        # In production, we'd iterate over discrete prescriptions
        med_dict = {
            "resourceType": "MedicationRequest",
            "id": str(uuid.uuid4()),
            "status": "active",
            "intent": "order",
            "medication": {"concept": {"text": encounter.rx_text}},
            "subject": {"reference": f"Patient/{encounter.customer_id}"},
            "authoredOn": encounter.created_at.isoformat()
        }
        requests.append(MedicationRequest.parse_obj(med_dict))
    return requests

def map_to_document_reference(encounter: Encounter) -> DocumentReference:
    """
    Creates a DocumentReference (Progress Note) for the full encounter.
    """
    # Base64 encode the transcript or summary
    note_content = encounter.rx_text or "Clinical encounter note."
    encoded_content = base64.b64encode(note_content.encode("utf-8")).decode("utf-8")
    
    doc_dict = {
        "resourceType": "DocumentReference",
        "id": str(uuid.uuid4()),
        "status": "current",
        "type": {
            "coding": [{"system": "http://loinc.org", "code": "11506-3", "display": "Progress note"}],
            "text": "Progress note"
        },
        "subject": {"reference": f"Patient/{encounter.customer_id}"},
        "date": encounter.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "content": [
            {
                "attachment": {
                    "contentType": "text/plain",
                    "data": encoded_content
                }
            }
        ],
        "context": [{"reference": f"Encounter/{encounter.id}"}]
    }
    return DocumentReference.parse_obj(doc_dict)

def map_to_flags(encounter: Encounter) -> List[Flag]:
    """
    Extracts CDS risk indicators from an encounter and returns a list of FHIR Flag resources.
    """
    flags = []
    if encounter.clinical_data and "cds" in encounter.clinical_data:
        cds = encounter.clinical_data["cds"]
        risks = cds.get("risks", [])
        for risk in risks:
            flag_dict = {
                "resourceType": "Flag",
                "id": str(uuid.uuid4()),
                "status": "active",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/flag-category",
                                "code": "clinical",
                                "display": "Clinical"
                            }
                        ]
                    }
                ],
                "code": {
                    "text": f"{risk.get('type')} - {risk.get('severity')} Severity. Recommendation: {risk.get('action_recommendation')}",
                    "coding": [
                        {
                            "system": "http://superhumanlydoctors.io/cds-risks",
                            "code": risk.get("type").lower().replace(" ", "-"),
                            "display": risk.get("type")
                        }
                    ]
                },
                "subject": {"reference": f"Patient/{encounter.customer_id}"},
                "author": {"display": "Superhumanly AI CDS Engine"}
            }
            flags.append(Flag.parse_obj(flag_dict))
    return flags

def map_encounter_to_bundle(encounter: Encounter, patient: Optional[Customer] = None) -> Bundle:
    """
    Combines all related resources into a FHIR transaction Bundle.
    """
    entries = []
    
    # 1. The Encounter itself
    fhir_enc = map_encounter_to_fhir(encounter, patient=patient)
    entries.append(BundleEntry(
        resource=fhir_enc,
        request=BundleEntryRequest(method="PUT", url=f"Encounter/{fhir_enc.id}")
    ))
    
    # 2. The Patient (if missing, but usually exists)
    if patient:
        fhir_pat = map_customer_to_patient(patient)
        entries.append(BundleEntry(
            resource=fhir_pat,
            request=BundleEntryRequest(method="PUT", url=f"Patient/{fhir_pat.id}")
        ))
        
    # 3. Conditions
    for cond in map_to_condition(encounter):
        entries.append(BundleEntry(
            resource=cond,
            request=BundleEntryRequest(method="POST", url="Condition")
        ))
        
    # 4. MedicationRequests
    for med in map_to_medication_request(encounter):
        entries.append(BundleEntry(
            resource=med,
            request=BundleEntryRequest(method="POST", url="MedicationRequest")
        ))
        
    # 5. DocumentReference
    doc_ref = map_to_document_reference(encounter)
    entries.append(BundleEntry(
        resource=doc_ref,
        request=BundleEntryRequest(method="POST", url="DocumentReference")
    ))
    
    # 6. Risk Flags (CDS)
    for flag in map_to_flags(encounter):
        entries.append(BundleEntry(
            resource=flag,
            request=BundleEntryRequest(method="POST", url="Flag")
        ))
    
    bundle_dict = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries
    }
    # Using entries directly in constructor because BundleEntry are already objects
    return Bundle(type="transaction", entry=entries)
