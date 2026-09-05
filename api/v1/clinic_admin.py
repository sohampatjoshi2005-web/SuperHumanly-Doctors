from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from app.api.v1.auth import get_current_clinic_admin, get_password_hash
from app.db import get_session
from app.db_models import User, UsageMeter, Clinic, Encounter, Customer
from sqlmodel import select, func

router = APIRouter(prefix="/clinic", tags=["clinic_admin"])

class DoctorCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class ClinicMember(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str]
    role: str
    created_at: Any

@router.get("/members", response_model=List[ClinicMember])
async def list_clinic_members(current_admin: User = Depends(get_current_clinic_admin)):
    """
    List all doctors and staff within the admin's clinic.
    """
    if not current_admin.clinic_id and current_admin.role != "admin":
         raise HTTPException(status_code=400, detail="Admin is not assigned to a clinic")

    with get_session() as session:
        statement = select(User)
        if current_admin.role != "admin":
            statement = statement.where(User.clinic_id == current_admin.clinic_id)
        
        members = session.exec(statement).all()
        return members

@router.post("/members", response_model=Dict[str, Any])
async def add_doctor_to_clinic(doctor_in: DoctorCreate, current_admin: User = Depends(get_current_clinic_admin)):
    """
    Add a new doctor to the clinic.
    """
    if not current_admin.clinic_id and current_admin.role != "admin":
         raise HTTPException(status_code=400, detail="Admin is not assigned to a clinic")

    with get_session() as session:
        # Check uniqueness
        existing = session.exec(select(User).where((User.username == doctor_in.username) | (User.email == doctor_in.email))).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username or email already exists")

        new_doctor = User(
            username=doctor_in.username,
            email=doctor_in.email,
            hashed_password=get_password_hash(doctor_in.password),
            full_name=doctor_in.full_name,
            role="doctor",
            clinic_id=current_admin.clinic_id,
            is_active=True
        )
        session.add(new_doctor)
        session.flush()

        # Init usage meter
        meter = UsageMeter(id=str(new_doctor.id))
        session.add(meter)
        session.commit()
        
        return {"status": "success", "doctor_id": new_doctor.id}

@router.get("/stats")
async def get_clinic_stats(current_admin: User = Depends(get_current_clinic_admin)):
    """
    Aggregate clinical intelligence for the entire clinic.
    """
    if not current_admin.clinic_id and current_admin.role != "admin":
         raise HTTPException(status_code=400, detail="Admin is not assigned to a clinic")

    with get_session() as session:
        clinic_id = current_admin.clinic_id
        
        # 1. Basic Counts
        doctor_ids = session.exec(select(User.id).where(User.clinic_id == clinic_id)).all()
        enc_count = session.exec(select(func.count(Encounter.id)).where(Encounter.clinic_id == clinic_id)).one()
        pat_count = session.exec(select(func.count(Customer.id)).where(Customer.clinic_id == clinic_id)).one()
        
        # 2. Staff Efficiency (Encounters per Doctor)
        staff_perf = []
        for d_id in doctor_ids:
            doctor = session.get(User, d_id)
            d_encs = session.exec(select(func.count(Encounter.id)).where(Encounter.doctor_id == d_id)).one()
            staff_perf.append({
                "name": doctor.full_name or doctor.username,
                "encounters": d_encs
            })
            
        # 3. Monthly Trends (Last 6 Months)
        # Simplified: Just count for now
        
        # 4. Top Diagnosis (Rough extraction from RX JSON)
        # In a real app, this would be a structured query on a Diagnosis table
        all_encs = session.exec(select(Encounter.rx_json).where(Encounter.clinic_id == clinic_id).limit(100)).all()
        diagnosis_map = {}
        for rx in all_encs:
            if rx and isinstance(rx, dict) and "diagnosis" in rx:
                diag = rx["diagnosis"].split(",")[0].strip() # Take primary
                diagnosis_map[diag] = diagnosis_map.get(diag, 0) + 1
        
        top_diagnoses = sorted(diagnosis_map.items(), key=lambda x: x[1], reverse=True)[:5]

        clinic = session.get(Clinic, clinic_id) if clinic_id else None
        
        return {
            "total_encounters": enc_count,
            "total_patients": pat_count,
            "team_size": len(doctor_ids),
            "clinic_name": clinic.name if clinic else "Master Admin View",
            "staff_performance": staff_perf,
            "top_diagnoses": [{"name": k, "count": v} for k, v in top_diagnoses]
        }

@router.get("/report/pdf")
async def export_clinic_report(current_admin: User = Depends(get_current_clinic_admin)):
    """
    Generate and download a professional PDF report for the clinic.
    """
    from app.services.reporting_service import generate_clinic_report_pdf
    from fastapi.responses import StreamingResponse
    
    stats = await get_clinic_stats(current_admin)
    clinic_name = stats.get("clinic_name", "Clinic Report")
    
    pdf_buffer = generate_clinic_report_pdf(clinic_name, stats)
    
    filename = f"Clinic_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/benchmarks/efficiency")
async def get_efficiency_benchmarks(current_admin: User = Depends(get_current_clinic_admin)):
    """
    Detailed time-to-sign analysis and documentation velocity.
    """
    if not current_admin.clinic_id:
         raise HTTPException(status_code=400, detail="Admin is not assigned to a clinic")
    
    from app.services.institutional_service import InstitutionalService
    return InstitutionalService.get_efficiency_benchmarks(current_admin.clinic_id)

@router.get("/benchmarks/accuracy")
async def get_accuracy_benchmarks(current_admin: User = Depends(get_current_clinic_admin)):
    """
    Rankings based on documentation precision and code alignment (AI vs. Human).
    """
    if not current_admin.clinic_id:
         raise HTTPException(status_code=400, detail="Admin is not assigned to a clinic")
    
    from app.services.institutional_service import InstitutionalService
    return InstitutionalService.get_diagnostic_accuracy_report(current_admin.clinic_id)
