import random
import uuid
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from app.db import engine
from app.db_models import Clinic, User, Customer, Encounter, IntelligenceSession, IntelligenceMessage
from app.api.v1.auth import get_password_hash

def seed_massive_data():
    with Session(engine) as session:
        print("🚀 Starting Massive Seeding Protocol...")
        
        # 1. Ensure Clinic exists
        clinic = session.exec(select(Clinic).where(Clinic.name == "Massive Test Hospital")).first()
        if not clinic:
            clinic = Clinic(
                name="Massive Test Hospital",
                address="456 Scaling St, Data City",
                contact_email="scaling@superhumanly.ai"
            )
            session.add(clinic)
            session.flush()
            print(f"✅ Created Clinic: {clinic.name}")
        
        # 2. Ensure Doctor exists
        doctor = session.exec(select(User).where(User.username == "test_doctor")).first()
        if not doctor:
            doctor = User(
                username="test_doctor",
                email="test_doctor@superhumanly.ai",
                hashed_password=get_password_hash("doctor123"),
                role="doctor",
                full_name="Dr. Data Scaler",
                clinic_id=clinic.id,
                is_active=True
            )
            session.add(doctor)
            session.flush()
            print(f"✅ Created Doctor: {doctor.username}")

        # 3. Create 50 Patients
        print("🚀 Creating 50 Patients...")
        patient_names = [
            "John Doe", "Jane Smith", "Robert Brown", "Emily Davis", "Michael Wilson",
            "Sarah Miller", "David Taylor", "Jessica Moore", "Christopher Anderson", "Ashley Thomas",
            "Matthew Jackson", "Amanda White", "Joshua Harris", "Melissa Martin", "Daniel Thompson",
            "Jennifer Garcia", "Andrew Martinez", "Stephanie Robinson", "James Clark", "Nicole Rodriguez",
            "Joseph Lewis", "Elizabeth Lee", "Ryan Walker", "Heather Hall", "Kevin Allen",
            "Kimberly Young", "Thomas Hernandez", "Amy King", "Charles Wright", "Michelle Lopez",
            "Brian Hill", "Angela Scott", "Edward Green", "Shirley Adams", "Ronald Baker",
            "Cynthia Gonzalez", "Anthony Nelson", "Dorothy Carter", "Donald Mitchell", "Lisa Perez",
            "Paul Roberts", "Nancy Turner", "Mark Phillips", "Karen Campbell", "George Parker",
            "Betty Evans", "Steven Edwards", "Sandra Collins", "Kenneth Stewart", "Donna Sanchez"
        ]
        
        patients = []
        for name in patient_names:
            p = Customer(
                name=name,
                doctor_id=doctor.id,
                clinic_id=clinic.id
            )
            session.add(p)
            patients.append(p)
        session.flush()

        # 4. Create 500 Encounters over last 60 days
        print("🚀 Creating 500 Encounters...")
        specialties = ["Cardiology", "Neurology", "Pediatrics", "Internal Medicine", "General Surgery"]
        complexities = ["High", "Moderate", "Low"]
        diagnoses = [
            "Hypertension (I10)", "Type 2 Diabetes Mellitus (E11.9)", "Acute Sinusitis (J01.90)",
            "Lower Back Pain (M54.5)", "Generalized Anxiety Disorder (F41.1)", "Acute Bronchitis (J20.9)",
            "Gastro-esophageal Reflux Disease (K21.9)", "Urinary Tract Infection (N39.0)", "Hyperlipidemia (E78.5)"
        ]

        now = datetime.now(timezone.utc)
        for i in range(500):
            p = random.choice(patients)
            days_ago = random.randint(0, 60)
            hours_ago = random.randint(0, 23)
            created_at = now - timedelta(days=days_ago, hours=hours_ago)
            
            enc = Encounter(
                doctor_id=doctor.id,
                clinic_id=clinic.id,
                customer_id=p.id,
                created_at=created_at,
                complexity=random.choice(complexities),
                diagnosis=random.choice(diagnoses),
                patient_summary=f"Follow-up for {random.choice(specialties)} case. Patient reports stable symptoms.",
                rx_text=f"Continue current regimen of {random.choice(['Lisinopril', 'Metformin', 'Amoxicillin'])}.",
                codes_json={"codes": [{"code": "I10", "description": "Hypertension"}]},
                documentation_duration_sec=random.randint(120, 600)
            )
            session.add(enc)
        
        # 5. Create Intelligence Sessions
        print("🚀 Creating Intelligence Sessions...")
        titles = ["Monthly Workload Analysis", "Population Health Risk", "Efficiency Audit Q1"]
        for title in titles:
            sess = IntelligenceSession(
                doctor_id=doctor.id,
                clinic_id=clinic.id,
                title=title
            )
            session.add(sess)
            session.flush()
            
            # Add some messages
            msg1 = IntelligenceMessage(
                session_id=sess.id,
                role="user",
                content=f"Analyze my {title}."
            )
            msg2 = IntelligenceMessage(
                session_id=sess.id,
                role="assistant",
                content="I have analyzed your clinical dataset. Your workload shows a 15% increase in high-complexity cases."
            )
            session.add(msg1)
            session.add(msg2)

        session.commit()
        print("✅ Massive Seeding Complete!")
        print(f"   - Clinic: {clinic.name}")
        print(f"   - Doctor: {doctor.username} (Password: doctor123)")
        print(f"   - Patients: {len(patient_names)}")
        print(f"   - Encounters: 500")

if __name__ == "__main__":
    seed_massive_data()
