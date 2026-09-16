from sqlmodel import SQLModel, create_engine, Session, select
from app.db_models import Customer, HMSRecord
from app.core.config import settings
import os

def migrate_and_seed():
    db_url = os.getenv("DATABASE_URL", settings.database_url)
    # Strip async driver for sync migration script
    db_url = db_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    print(f"🚀 Migrating EHR models at {db_url}")
    engine = create_engine(db_url)
    
    # Create tables
    SQLModel.metadata.create_all(engine)
    print("✅ Tables created successfully.")

    with Session(engine) as session:
        # Check for existing customers to seed HMS records for
        customers = session.exec(select(Customer)).all()
        print(f"🔍 Found {len(customers)} customers.")
        
        for customer in customers:
            # Check if record already exists
            existing = session.exec(select(HMSRecord).where(HMSRecord.customer_id == customer.id)).first()
            if not existing:
                print(f"🌱 Seeding HMSRecord for {customer.name}")
                hms = HMSRecord(
                    customer_id=customer.id,
                    diagnosis="Initial baseline assessment (Simulated)",
                    billing_codes={"codes": ["99213", "Z00.00"]},
                    rx_summary="Patient on standard protocol.",
                    system_provider="Epic"
                )
                session.add(hms)
        
        session.commit()
        print("✅ Seeding complete.")

if __name__ == "__main__":
    migrate_and_seed()
