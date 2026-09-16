import os
import sys
import time
import asyncio
import random
import uuid
from datetime import datetime, timedelta

# Add current directory to path
sys.path.append(os.getcwd())

from app.db import get_session, init_db, engine
from app.db_models import User, Customer, Encounter, Clinic
from app.api.v1.auth import get_password_hash
from sqlalchemy import text

async def run_stress_test(count: int = 1000):
    print(f"🔥 Starting Institutional Stress Test ({count} encounters)...")
    
    init_db()
    
    with get_session() as session:
        # Get existing clinic or create one
        clinic = session.exec(text("SELECT * FROM clinic LIMIT 1")).first()
        if not clinic:
            print("❌ No clinic found. Run seeder first.")
            return
            
        clinic_id = clinic.id
        doctor = session.exec(text(f"SELECT * FROM \"user\" WHERE clinic_id = '{clinic_id}' AND role = 'doctor' LIMIT 1")).first()
        patient = session.exec(text(f"SELECT * FROM customer WHERE clinic_id = '{clinic_id}' LIMIT 1")).first()
        
        if not doctor or not patient:
            print("❌ No doctor or patient found. Run seeder first.")
            return

        print(f"Injecting {count} encounters into clinic {clinic_id}...")
        
        start_injection = time.time()
        for i in range(count):
            days_ago = random.randint(0, 90) # 3-month history
            created_at = datetime.utcnow() - timedelta(days=days_ago)
            
            enc = Encounter(
                id=str(uuid.uuid4()),
                customer_id=patient.id,
                doctor_id=doctor.id,
                clinic_id=clinic_id,
                cleaned_text="Stress test encounter data.",
                complexity=random.choice(["High", "Moderate", "Low"]),
                created_at=created_at,
                status="Completed",
                documentation_duration_sec=random.randint(30, 300),
                codes_json={"codes": [{"code": "Z00.00"}]},
                original_codes_json={"codes": [{"code": "Z00.00"}]}
            )
            session.add(enc)
            if i % 100 == 0:
                session.flush()
                
        session.commit()
        injection_time = time.time() - start_injection
        print(f"✅ Injection complete in {injection_time:.2f}s")

        # --- Latency Audit ---
        print("\n📊 Auditing Query Latency...")
        
        # 1. Institutional Stats (Large Aggregation)
        start_q = time.time()
        res = session.execute(text(f"SELECT count(*) FROM encounter WHERE clinic_id = '{clinic_id}'")).scalar()
        lat_count = (time.time() - start_q) * 1000
        print(f"Institutional Count Latency: {lat_count:.2f}ms (Result: {res})")

        # 2. Benchmark Aggregation (Complexity)
        start_q = time.time()
        res = session.execute(text(f"SELECT complexity, count(*) FROM encounter WHERE clinic_id = '{clinic_id}' GROUP BY complexity")).all()
        lat_bench = (time.time() - start_q) * 1000
        print(f"Complexity Aggregation Latency: {lat_bench:.2f}ms")

        # 3. Time-to-Sign Index Audit
        start_q = time.time()
        res = session.execute(text(f"SELECT avg(documentation_duration_sec) FROM encounter WHERE doctor_id = '{doctor.id}'")).scalar()
        lat_tts = (time.time() - start_q) * 1000
        print(f"TTS Average Latency (Indexed): {lat_tts:.2f}ms")

        # Verify Index Usage
        print("\n🔍 Verifying Index Usage (EXPLAIN)...")
        explain = session.execute(text(f"EXPLAIN QUERY PLAN SELECT count(*) FROM encounter WHERE clinic_id = '{clinic_id}'")).all()
        for line in explain:
            print(f"QUERY PLAN: {line}")
            if "USING INDEX" in str(line):
                print("✅ Index successfully utilized.")

    print("\n🚀 STRESS TEST COMPLETE")

if __name__ == "__main__":
    asyncio.run(run_stress_test(2000))
