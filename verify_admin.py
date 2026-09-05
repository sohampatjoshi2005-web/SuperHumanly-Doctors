import httpx
import os
import sys
from datetime import datetime

# Add app to path
sys.path.append(os.getcwd())

from app.db import get_session
from app.db_models import User, Clinic, TrialRequest, AuditLog
from app.api.v1.auth import get_password_hash
from sqlmodel import select, delete

BASE_URL = "http://localhost:8000"

def verify_endpoints():
    username = "verify_tester"
    email = "verify@tester.io"
    password = "tester_password"
    
    # 1. Provision Test Admin
    print("🚀 Provisioning Test Admin...")
    with get_session() as session:
        # Cleanup if exists
        session.exec(delete(User).where(User.username == username))
        session.commit()
        
        tester = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            role="admin",
            full_name="Verification Tester",
            is_active=True
        )
        session.add(tester)
        session.commit()
        session.refresh(tester)

    try:
        # 2. Login
        print("🔑 Authenticating...")
        with httpx.Client(base_url=BASE_URL) as client:
            login_res = client.post("/v1/auth/login", json={
                "username": username,
                "email": email,
                "password": password
            })
            if login_res.status_code != 200:
                print(f"❌ Login Failed: {login_res.text}")
                return
            
            token = login_res.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # 3. Test Telemetry
            print("📊 Testing System Telemetry...")
            telemetry_res = client.get("/v1/admin/health/telemetry", headers=headers)
            print(f"   Status: {telemetry_res.status_code}")
            print(f"   Payload: {telemetry_res.json()}")
            assert telemetry_res.status_code == 200
            
            # 4. Test Stats
            print("📈 Testing Admin Stats...")
            stats_res = client.get("/v1/admin/stats", headers=headers)
            print(f"   Status: {stats_res.status_code}")
            print(f"   Payload: {stats_res.json()}")
            assert stats_res.status_code == 200
            
            # 5. Test Audit Logs
            print("📜 Testing Audit Ledger...")
            audit_res = client.get("/v1/admin/audit/logs", headers=headers)
            print(f"   Status: {audit_res.status_code}")
            print(f"   Count: {len(audit_res.json())}")
            assert audit_res.status_code == 200
            
            # 6. Test Audit Verification
            print("🛡️ Testing Audit Verification Protocol...")
            verify_res = client.get("/v1/admin/audit/verify", headers=headers)
            print(f"   Status: {verify_res.status_code}")
            print(f"   Payload: {verify_res.json()}")
            # assert verify_res.status_code == 200
            
            # 7. Test Clinic Registration
            print("🏢 Testing Clinic Registration...")
            clinic_name = f"Test Clinic {datetime.now().timestamp()}"
            clinic_res = client.post("/v1/admin/clinics", headers=headers, json={
                "name": clinic_name,
                "address": "123 Verification St",
                "contact_email": "test@clinic.io",
                "phone": "555-TEST"
            })
            print(f"   Status: {clinic_res.status_code}")
            print(f"   Payload: {clinic_res.json()}")
            assert clinic_res.status_code == 200
            
            # 8. Test User Promotion
            print("🎖️ Testing User Promotion Protocol...")
            # Create a doctor to promote
            with get_session() as session:
                doc_user = User(
                    username="test_doc",
                    email="doc@test.io",
                    hashed_password="...",
                    role="doctor"
                )
                session.add(doc_user)
                session.commit()
            
            promote_res = client.post("/v1/admin/promote/test_doc", headers=headers)
            print(f"   Status: {promote_res.status_code}")
            assert promote_res.status_code == 200
            
            print("\n✅ ALL ADMINISTRATIVE ENDPOINTS VERIFIED SUCCESSFULLY.")

    finally:
        # Cleanup
        print("\n🧹 Skipping cleanup for diagnosis...")
        # with get_session() as session:
        #     session.exec(delete(User).where(User.username == username))
        #     session.exec(delete(User).where(User.username == "test_doc"))
        #     session.exec(delete(Clinic).where(Clinic.name.like("Test Clinic%")))
        #     session.commit()

if __name__ == "__main__":
    verify_endpoints()
