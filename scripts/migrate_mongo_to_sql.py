import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from sqlmodel import Session, select
from app.db import engine, init_db
from app.db_models import User, Clinic, TrialRequest, AuditLog
from app.core.config import settings
import certifi

async def migrate():
    # 1. Initialize SQL Database (Create tables)
    print("🚀 Initializing SQL Database...")
    init_db()

    # 2. Connect to MongoDB
    print(f"🔗 Connecting to MongoDB: {settings.mongodb_url[:20]}...")
    client = AsyncIOMotorClient(
        settings.mongodb_url,
        tlsCAFile=certifi.where()
    )
    
    try:
        # Attempt to get the database from the URI or use default
        db = client.get_default_database()
    except Exception:
        db = client.get_database("healthcare_db")

    with Session(engine) as session:
        # --- Migrate Clinics ---
        print("🏥 Migrating Clinics...")
        mongo_clinics = await db.clinics.find().to_list(length=None)
        for mc in mongo_clinics:
            # Check if exists
            existing = session.get(Clinic, str(mc["_id"]))
            if existing: continue
            
            clinic = Clinic(
                id=str(mc["_id"]),
                name=mc["name"],
                address=mc.get("address"),
                contact_email=mc.get("contact_email"),
                phone=mc.get("phone"),
                is_active=mc.get("is_active", True),
                created_at=mc.get("created_at")
            )
            session.add(clinic)
        session.commit()
        print(f"✅ Migrated {len(mongo_clinics)} clinics.")

        # --- Migrate Users ---
        print("👤 Migrating Users...")
        mongo_users = await db.users.find().to_list(length=None)
        for mu in mongo_users:
            existing = session.get(User, str(mu["_id"]))
            if existing: continue

            user = User(
                id=str(mu["_id"]),
                username=mu["username"],
                email=mu["email"],
                hashed_password=mu["hashed_password"],
                is_active=mu.get("is_active", True),
                role=mu.get("role", "doctor"),
                clinic_id=str(mu["clinic_id"]) if mu.get("clinic_id") else None,
                full_name=mu.get("full_name"),
                institution=mu.get("institution"),
                trial_expires_at=mu.get("trial_expires_at"),
                is_unlimited=mu.get("is_unlimited", False),
                created_at=mu.get("created_at")
            )
            session.add(user)
        session.commit()
        print(f"✅ Migrated {len(mongo_users)} users.")

        # --- Migrate Trial Requests ---
        print("🧪 Migrating Trial Requests...")
        mongo_trials = await db.trial_requests.find().to_list(length=None)
        for mt in mongo_trials:
            existing = session.get(TrialRequest, str(mt["_id"]))
            if existing: continue

            trial = TrialRequest(
                id=str(mt["_id"]),
                full_name=mt["full_name"],
                email=mt["email"],
                institution=mt["institution"],
                professional_role=mt["professional_role"],
                use_case=mt["use_case"],
                status=mt.get("status", "pending"),
                created_at=mt.get("created_at"),
                processed_at=mt.get("processed_at"),
                processed_by=mt.get("processed_by")
            )
            session.add(trial)
        session.commit()
        print(f"✅ Migrated {len(mongo_trials)} trial requests.")

        # --- Migrate Audit Logs ---
        print("📜 Migrating Audit Logs (limit 1000 for safety)...")
        mongo_audits = await db.audit_logs.find().sort("timestamp", -1).to_list(length=1000)
        for ma in mongo_audits:
            existing = session.get(AuditLog, str(ma["_id"]))
            if existing: continue

            audit = AuditLog(
                id=str(ma["_id"]),
                actor=ma["actor"],
                action=ma["action"],
                resource_type=ma["resource_type"],
                resource_id=ma["resource_id"],
                ip_address=ma.get("ip_address"),
                timestamp=ma.get("timestamp")
            )
            session.add(audit)
        session.commit()
        print(f"✅ Migrated {len(mongo_audits)} audit logs.")

    print("🏁 Migration Complete!")

if __name__ == "__main__":
    asyncio.run(migrate())
