import os
import sys
from datetime import datetime, timedelta
import random
import uuid

# Add current directory to path
sys.path.append(os.getcwd())

from app.db import get_session, init_db
from app.db_models import User, Customer, Encounter, Clinic
from app.api.v1.auth import get_password_hash

def seed_institutional_data():
    print("🚀 Seeding Institutional Clinical Data (30-Day History)...")
    
    from app.db import engine
    from sqlmodel import SQLModel
    
    # Clean drop and recreate for fresh start
    print("🧹 Cleaning database...")
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    
    with get_session() as session:
        # 1. Create Institutional Clinic
        clinic_id = str(uuid.uuid4())
        clinic = Clinic(
            id=clinic_id,
            name="Superhumanly General Hospital",
            address="456 Analytics Ave, Metro City",
            contact_email="admin@sgh-hospital.org"
        )
        session.add(clinic)
        
        # 2. Create Doctors
        doctors = []
        specialties = ["Cardiology", "Neurology", "Pediatrics", "Internal Medicine", "Surgery"]
        for i in range(5):
            doc_id = str(uuid.uuid4())
            doc = User(
                id=doc_id,
                username=f"doctor_{i+1}",
                email=f"doc{i+1}@sgh-hospital.org",
                hashed_password=get_password_hash("doctor123"),
                full_name=f"Dr. {['Smith', 'Jones', 'Williams', 'Brown', 'Davis'][i]}",
                role="doctor",
                clinic_id=clinic_id,
                is_active=True
            )
            session.add(doc)
            doctors.append(doc)
            
        # 3. Create Clinic Admin
        admin = User(
            username="hospital_admin",
            email="admin@sgh-hospital.org",
            hashed_password=get_password_hash("admin123"),
            full_name="Hospital Director",
            role="clinic_admin",
            clinic_id=clinic_id,
            is_active=True
        )
        session.add(admin)
        
        session.commit()
        
        # 4. Create Patients & Encounters
        print(f"Creating patients and encounters for {len(doctors)} doctors...")
        
        diagnoses = [
            "Type 2 Diabetes Mellitus", "Hypertension", "Acute Bronchitis", 
            "Gastroesophageal reflux disease", "Hyperlipidemia", "Migraine",
            "Atrial Fibrillation", "Osteoarthritis", "Major Depressive Disorder"
        ]
        
        complexities = ["High", "Moderate", "Low"]
        
        total_encounters = 0
        for doc in doctors:
            # Each doctor has 10-15 patients
            for p_idx in range(random.randint(10, 15)):
                patient_id = str(uuid.uuid4())
                patient = Customer(
                    id=patient_id,
                    name=f"Patient {uuid.uuid4().hex[:6]}",
                    clinic_id=clinic_id,
                    doctor_id=doc.id
                )
                session.add(patient)
                
                # Each patient has 1-5 encounters over the last 30 days
                for e_idx in range(random.randint(1, 5)):
                    days_ago = random.randint(0, 30)
                    created_at = datetime.utcnow() - timedelta(days=days_ago)
                    
                    complexity = random.choice(complexities)
                    diag = random.choice(diagnoses)
                    
                    encounter = Encounter(
                        id=str(uuid.uuid4()),
                        customer_id=patient_id,
                        doctor_id=doc.id,
                        clinic_id=clinic_id,
                        cleaned_text=f"Encounter for {diag}. Complexity is {complexity}.",
                        complexity=complexity,
                        created_at=created_at,
                        status="Completed",
                        rx_text=f"Continue existing meds for {diag}.",
                        rx_json={"medicines": [{"name": "Standard Med", "dosage": "daily"}]},
                        codes_json={"codes": [{"code": "Z00.00", "description": "General exam"}]},
                        original_codes_json={"codes": [{"code": "Z00.00", "description": "General exam"}]},
                        documentation_duration_sec=random.randint(30, 120),
                        rounds_report={
                            "consensus": "Management appropriate.",
                            "status": "Verified",
                            "internist_notes": "Consistent with guidelines.",
                            "pharmacist_notes": "No drug interactions."
                        }
                    )
                    session.add(encounter)
                    total_encounters += 1
            
        session.commit()
        print(f"✅ Seeding Complete. Created 1 Clinic, {len(doctors)} Doctors, and {total_encounters} Encounters.")
        print(f"🔑 Use 'hospital_admin' / 'admin123' to view the Institutional Dashboard.")

if __name__ == "__main__":
    seed_institutional_data()
