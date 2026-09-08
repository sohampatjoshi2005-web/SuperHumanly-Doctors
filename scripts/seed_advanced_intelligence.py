import asyncio
from app.db import get_session
from app.db_models import Customer, Encounter, User
from sqlmodel import select
from datetime import datetime, timedelta
import uuid

def seed_advanced_data():
    with get_session() as session:
        # 1. Get a test doctor
        doctor = session.exec(select(User).where(User.username == "admin")).first()
        if not doctor:
            print("❌ Admin doctor not found. Run standard seed first.")
            return

        # 2. Create a "High Risk" Patient
        patient_name = "Longitudinal Test Patient"
        customer = session.exec(select(Customer).where(Customer.name == patient_name)).first()
        if not customer:
            customer = Customer(name=patient_name, doctor_id=str(doctor.id), clinic_id=doctor.clinic_id)
            session.add(customer)
            session.commit()
            session.refresh(customer)
            print(f"✅ Created patient: {patient_name}")
        
        # 3. Create Encounter History with creatinine rise (AKI Trigger)
        print("🚀 Generating clinical timeline...")
        
        # Baseline Encounter (3 days ago)
        e1 = Encounter(
            customer_id=customer.id,
            doctor_id=str(doctor.id),
            clinic_id=doctor.clinic_id,
            created_at=datetime.utcnow() - timedelta(days=3),
            transcript="Patient seen for baseline labs.",
            patient_summary="Routine follow-up.",
            clinical_data={"creatinine": 1.0, "sbp": 120, "dbp": 80},
            complexity="Low"
        )
        session.add(e1)

        # Recent Encounter (24h later - rise to 1.4)
        e2 = Encounter(
            customer_id=customer.id,
            doctor_id=str(doctor.id),
            clinic_id=doctor.clinic_id,
            created_at=datetime.utcnow() - timedelta(hours=24),
            transcript="Patient reports decreased urine output.",
            patient_summary="Acute presentation with fluid issues.",
            clinical_data={"creatinine": 1.4, "sbp": 145, "dbp": 95},
            complexity="Moderate"
        )
        session.add(e2)

        # 4. Generate some general encounters for the heatmap
        print("🔥 Generating 100 encounters for heatmap density...")
        import random
        for i in range(100):
            # Random time in last 7 days
            random_days = random.randint(0, 6)
            random_hours = random.randint(0, 23)
            random_mins = random.randint(0, 59)
            
            # Skew towards 9am-5pm
            if random.random() > 0.7:
                random_hours = random.randint(9, 17)
                
            enc_time = datetime.utcnow() - timedelta(days=random_days, hours=random_hours, minutes=random_mins)
            
            e = Encounter(
                customer_id=customer.id,
                doctor_id=str(doctor.id),
                clinic_id=doctor.clinic_id,
                created_at=enc_time,
                transcript="Simulated encounter for analytics.",
                patient_summary="Automated data point.",
                complexity=random.choice(["High", "Moderate", "Low"]),
                clinical_data={"sbp": random.randint(110, 160), "dbp": random.randint(70, 100)}
            )
            session.add(e)

        session.commit()
        print("✅ Advanced Intelligence Seeding Complete.")

if __name__ == "__main__":
    seed_advanced_data()
