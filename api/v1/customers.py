from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlmodel import select
from app.api.v1.auth import get_current_user
from app.db_models import User, AuditLog, Customer, Encounter
from app.db import get_session, scoped_select, commit_audit_log


router = APIRouter(prefix="/customers", tags=["customers"])


class EncounterHistory(BaseModel):
    id: str
    created_at: datetime
    diagnosis: Optional[str] = None
    patient_summary: str = ""
    rx_json: Optional[Dict[str, Any]] = None


class CustomerCreate(BaseModel):
    name: str


class CustomerRead(BaseModel):
    """API response shape — do not use SQLModel table class as response_model (serializes as {})."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    doctor_id: str
    clinic_id: Optional[str] = None
    created_at: datetime


def to_customer_read(customer: Customer) -> CustomerRead:
    return CustomerRead.model_validate(customer)


def require_customer_access(customer_id: str, current_user: User) -> Customer:
    """Ensure the patient exists and the caller may use it for clinical processing."""
    with get_session() as session:
        customer = session.get(Customer, customer_id)
        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Patient not found. Select or create a patient in the registry.",
            )

        is_owner = customer.doctor_id == str(current_user.id)
        is_clinic_admin = (
            current_user.role == "clinic_admin"
            and customer.clinic_id == current_user.clinic_id
        )
        is_master_admin = current_user.role == "admin"

        if not (is_owner or is_clinic_admin or is_master_admin):
            raise HTTPException(status_code=403, detail="Access denied to this patient record")

        return customer


@router.get("/{customer_id}/history", response_model=List[EncounterHistory])
async def get_customer_history(
    customer_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
) -> List[EncounterHistory]:
    with get_session() as session:
        customer = session.get(Customer, customer_id)
        if not customer:
             raise HTTPException(status_code=404, detail="customer not found")
             
        # PERMISSION CHECK (Inherit from list_customer_encounters logic)
        is_owner = customer.doctor_id == str(current_user.id)
        is_clinic_admin = current_user.role == "clinic_admin" and customer.clinic_id == current_user.clinic_id
        is_master_admin = current_user.role == "admin"
        
        if not (is_owner or is_clinic_admin or is_master_admin):
            raise HTTPException(status_code=403, detail="Access denied to this patient history")

        stmt = (
            scoped_select(Encounter)
            .where(Encounter.customer_id == customer_id)
            .order_by(Encounter.created_at.desc())
        )
        
        encounters = session.exec(stmt).all()
        
        # Mapping to EncounterHistory (summarized schema)
        history = [
            EncounterHistory(
                id=e.id,
                created_at=e.created_at,
                diagnosis=e.diagnosis,
                patient_summary=e.patient_summary,
                rx_json=e.rx_json
            ) for e in encounters
        ]
        
        client_ip = request.client.host if request.client else "unknown"
        audit = AuditLog(
            actor=current_user.username,
            action="READ_CUSTOMER_HISTORY",
            resource_type="Customer",
            resource_id=customer_id,
            ip_address=client_ip
        )
        commit_audit_log(session, audit)
        
        return history





@router.get("", response_model=List[CustomerRead])
async def list_customers(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> List[CustomerRead]:
    with get_session() as session:
        # DOCTORS see only their patients. 
        # CLINIC_ADMINS see all patients in their clinic (via scoped_select).
        statement = scoped_select(Customer)
        
        if current_user.role == "doctor":
            statement = statement.where(Customer.doctor_id == str(current_user.id))
        elif current_user.role == "admin":
            statement = select(Customer) # Master admin bypasses scope
            
        statement = statement.order_by(Customer.created_at.desc())
        
        client_ip = request.client.host if request.client else "unknown"
        audit = AuditLog(
            actor=current_user.username,
            action="LIST_CUSTOMERS",
            resource_type="Customer",
            resource_id="ALL",
            ip_address=client_ip,
            extra_metadata={"clinic_id": current_user.clinic_id}
        )
        customers = [to_customer_read(c) for c in session.exec(statement)]
        commit_audit_log(session, audit)
        return customers


@router.post("", response_model=CustomerRead)
def create_customer(
    payload: CustomerCreate, 
    current_user: User = Depends(get_current_user)
) -> CustomerRead:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    
    customer = Customer(
        name=name, 
        doctor_id=str(current_user.id),
        clinic_id=current_user.clinic_id
    )
    with get_session() as session:
        session.add(customer)
        session.commit()
        session.refresh(customer)
        return to_customer_read(customer)


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: str, 
    request: Request,
    current_user: User = Depends(get_current_user)
) -> CustomerRead:
    with get_session() as session:
        customer = session.get(Customer, customer_id)
        if not customer:
             raise HTTPException(status_code=404, detail="customer not found")
        
        # PERMISSION CHECK
        is_owner = customer.doctor_id == str(current_user.id)
        is_clinic_admin = current_user.role == "clinic_admin" and customer.clinic_id == current_user.clinic_id
        is_master_admin = current_user.role == "admin"

        if not (is_owner or is_clinic_admin or is_master_admin):
            raise HTTPException(status_code=403, detail="Access denied to this patient record")
            
        client_ip = request.client.host if request.client else "unknown"
        audit = AuditLog(
            actor=current_user.username,
            action="READ_CUSTOMER",
            resource_type="Customer",
            resource_id=customer_id,
            ip_address=client_ip
        )
        commit_audit_log(session, audit)
        
        return to_customer_read(customer)


@router.get("/{customer_id}/encounters", response_model=List[Encounter])
async def list_customer_encounters(
    customer_id: str, 
    request: Request,
    current_user: User = Depends(get_current_user)
) -> List[Encounter]:
    with get_session() as session:
        customer = session.get(Customer, customer_id)
        if not customer:
             raise HTTPException(status_code=404, detail="customer not found")
             
        # PERMISSION CHECK
        is_owner = customer.doctor_id == str(current_user.id)
        is_clinic_admin = current_user.role == "clinic_admin" and customer.clinic_id == current_user.clinic_id
        is_master_admin = current_user.role == "admin"
        
        # DEBUG LOG
        print(f"DEBUG: list_customer_encounters - user={current_user.username} role={current_user.role} user_clinic={current_user.clinic_id} patient_clinic={customer.clinic_id} is_owner={is_owner} is_admin={is_master_admin} is_clinic_admin={is_clinic_admin}")

        if not (is_owner or is_clinic_admin or is_master_admin):
            raise HTTPException(status_code=403, detail="Access denied to this patient registry")

        stmt = (
            scoped_select(Encounter)
            .where(Encounter.customer_id == customer_id)
            .order_by(Encounter.created_at.desc())
        )
        # Note: If we wanted to hide specific encounters from colleagues, we'd add another check here.
        # For now, if you can see the customer, you can see their encounters in the same clinic.
        
        client_ip = request.client.host if request.client else "unknown"
        audit = AuditLog(
            actor=current_user.username,
            action="LIST_CUSTOMER_ENCOUNTERS",
            resource_type="Customer",
            resource_id=customer_id,
            ip_address=client_ip
        )
        encounters = list(session.exec(stmt))
        commit_audit_log(session, audit)
        return encounters




