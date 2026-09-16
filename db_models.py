from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import SQLModel, Field, Index


def _utcnow() -> datetime:
    return datetime.utcnow()


class Customer(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    doctor_id: str = Field(index=True) # ID of the doctor who owns this customer
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    name: str = Field(index=True)
    fhir_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class Encounter(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    doctor_id: str = Field(index=True) # ID of the doctor who owns this encounter
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    customer_id: str = Field(index=True, foreign_key="customer.id")
    created_at: datetime = Field(default_factory=_utcnow, index=True)

    __table_args__ = (
        Index("ix_encounter_clinic_created", "clinic_id", "created_at"),
        Index("ix_encounter_doctor_created", "doctor_id", "created_at"),
    )

    audio_filename: Optional[str] = Field(default=None)
    transcript: str = Field(default="")
    diagnosis: Optional[str] = Field(default=None)
    patient_summary: str = Field(default="")

    rx_json: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    rx_text: str = Field(default="")
    
    # Billing & Reimbursement Support
    vitals_check: Optional[bool] = Field(default=None)
    complexity: Optional[str] = Field(default=None) # High, Moderate, Low
    codes_reasoning: Optional[str] = Field(default=None)
    codes_json: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    # [NEW] Benchmarking Fields
    original_codes_json: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    documentation_duration_sec: Optional[int] = Field(default=None)
    confidence_score: Optional[float] = Field(default=None)

    email_to: Optional[str] = Field(default=None)
    email_subject: Optional[str] = Field(default=None)
    email_status: Optional[str] = Field(default=None)
    email_message_id: Optional[str] = Field(default=None)
    
    # Clinical Data for Intelligence & Analytics
    clinical_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    rounds_report: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    fhir_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )


class UsageMeter(SQLModel, table=True):
    id: str = Field(primary_key=True)  # Links to User.id (MongoDB string)
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    trial_started_at: datetime = Field(default_factory=_utcnow, index=True)
    usage_count: int = Field(default=0)


class UpgradeRequest(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    doctor_id: str = Field(index=True)
    full_name: str
    clinic_name: str
    phone_number: str
    requested_at: datetime = Field(default_factory=_utcnow, index=True)
    status: str = Field(default="pending")


class Clinic(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(unique=True, index=True)
    address: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = Field(default=True)
    is_shared_registry: bool = Field(default=True) # Whether doctors share patients
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    role: str = Field(default="doctor") # 'doctor', 'clinic_admin', or 'admin'
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    full_name: Optional[str] = None
    institution: Optional[str] = None
    trial_expires_at: Optional[datetime] = None
    is_unlimited: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class TrialRequest(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    full_name: str
    email: str = Field(unique=True, index=True)
    institution: str
    professional_role: str
    use_case: str
    status: str = Field(default="pending") # 'pending', 'approved', 'rejected'
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None # Admin username


class AuditLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    actor: str = Field(index=True)
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    action: str = Field(index=True)
    resource_type: str = Field(index=True)
    resource_id: str = Field(index=True)
    ip_address: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow, index=True)
    extra_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    
    # Security & Integrity (Hash Chaining)
    prev_hash: Optional[str] = Field(default=None, description="SHA-256 of the previous audit log entry")
    event_hash: Optional[str] = Field(default=None, description="SHA-256 of this entry including data + prev_hash")
    
    # Note: Use 'created_at' if timestamp is ambiguous, but here 'timestamp' is used.
    # Re-mapped to created_at in some services.


class IntelligenceSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    doctor_id: str = Field(index=True)
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    title: str = Field(default="New Analysis")
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow)


class IntelligenceMessage(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(index=True, foreign_key="intelligencesession.id")
    role: str # 'user' or 'assistant'
    content: str
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class EHRSystem(SQLModel, table=True):
    """
    Defines a connected EHR system (e.g. Epic, Cerner).
    """
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(unique=True, index=True) # Epic, Cerner, Athena, etc.
    status: str = Field(default="Active") # Active, Standby, Offline
    base_url: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)


class HMSRecord(SQLModel, table=True):
    """
    Simulates a record in an external Hospital Management System (HMS).
    Used for EHR Sync conflict resolution.
    """
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    customer_id: str = Field(unique=True, index=True, foreign_key="customer.id")
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    system_id: Optional[str] = Field(default=None, index=True, foreign_key="ehrsystem.id")
    diagnosis: Optional[str] = Field(default=None)
    billing_codes: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    rx_summary: Optional[str] = Field(default=None)
    fhir_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql")),
    )
    last_sync_at: datetime = Field(default_factory=_utcnow)
    system_provider: str = Field(default="Epic") # Legacy field, will migrate to system_id

class SmartConnection(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    doctor_id: str = Field(index=True)
    clinic_id: Optional[str] = Field(default=None, index=True)
    fhir_iss: str = Field(index=True) # FHIR Server URL
    access_token: str # Should be encrypted in prod
    refresh_token: Optional[str] = None
    expires_at: datetime
    patient_context_id: Optional[str] = None # Patient ID from launch context
    created_at: datetime = Field(default_factory=_utcnow)

class ExternalResource(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    doctor_id: str = Field(index=True)
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    patient_id: str = Field(index=True)
    resource_type: str = Field(index=True) # e.g. "MedicationRequest", "Observation"
    fhir_id: str = Field(index=True) # ID on external server
    payload: Dict[str, Any] = Field(sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    last_synced_at: datetime = Field(default_factory=_utcnow)

class SyncLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    doctor_id: str = Field(index=True)
    clinic_id: Optional[str] = Field(default=None, index=True, foreign_key="clinic.id")
    patient_id: str = Field(index=True)
    direction: str = Field(index=True) # INBOUND, OUTBOUND
    status: str = Field(index=True) # SUCCESS, FAILURE
    resource_summary: str
    error_detail: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)

class Referral(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    encounter_id: str = Field(index=True, foreign_key="encounter.id")
    doctor_id: str = Field(index=True)
    patient_id: str = Field(index=True, foreign_key="customer.id")
    specialty: str = Field(index=True) # e.g. Cardiology
    reason: str
    priority: str = Field(default="Routine") # Routine, Urgent, Stat
    letter_text: Optional[str] = Field(default=None)
    insurance_notes: Optional[str] = Field(default=None)
    status: str = Field(default="Draft") # Draft, Sent, Completed
    created_at: datetime = Field(default_factory=_utcnow, index=True)

class PatientFollowup(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    encounter_id: str = Field(index=True, foreign_key="encounter.id")
    doctor_id: str = Field(index=True)
    patient_id: str = Field(index=True, foreign_key="customer.id")
    instruction: str
    due_date: datetime = Field(index=True)
    status: str = Field(default="Pending") # Pending, Sent, Completed
    created_at: datetime = Field(default_factory=_utcnow, index=True)

class AdherenceLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    patient_id: str = Field(index=True, foreign_key="customer.id")
    medication_name: str = Field(index=True)
    taken_status: bool = Field(default=True) # True = Taken, False = Missed
    timestamp: datetime = Field(default_factory=_utcnow, index=True)

class VaultRoot(SQLModel, table=True):
    """
    Stores the genesis hash for a clinic's audit vault.
    """
    clinic_id: str = Field(primary_key=True, foreign_key="clinic.id")
    genesis_hash: str = Field(description="The starting hash for the audit chain")
    created_at: datetime = Field(default_factory=_utcnow)


