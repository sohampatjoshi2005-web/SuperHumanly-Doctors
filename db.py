from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from app.core.config import settings
import app.db_models # Ensure all models are loaded


# Clean up database URL and ensure driver compatibility
base_url = settings.database_url
if "+asyncpg" in base_url:
    sync_url = base_url.replace("+asyncpg", "+psycopg2")
    async_url = base_url
elif "+psycopg2" in base_url:
    sync_url = base_url
    async_url = base_url.replace("+psycopg2", "+asyncpg")
else:
    # Handle generic postgres:// or sqlite://
    sync_url = base_url.replace("postgresql://", "postgresql+psycopg2://")
    async_url = base_url.replace("postgresql://", "postgresql+asyncpg://").replace("sqlite://", "sqlite+aiosqlite://")

_is_sqlite = sync_url.startswith("sqlite")

_engine_kwargs: dict = {
    "echo": False,
    "pool_pre_ping": True,
}
if _is_sqlite:
    # WAL + busy_timeout reduce "database is locked" under parallel dev traffic.
    _engine_kwargs.update(
        connect_args={"timeout": 30},
        poolclass=NullPool,
    )
else:
    _engine_kwargs.update(
        pool_size=20,
        max_overflow=10,
        pool_recycle=3600,
    )

engine = create_engine(sync_url, **_engine_kwargs)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

# Async engine for high-performance queries
try:
    async_engine = create_async_engine(
        async_url,
        echo=False,
        pool_size=20,
        max_overflow=10,
    )
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
except Exception as e:
    print(f"Warning: Async database setup failed: {e}")
    async_engine = None
    async_session_maker = None


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def seed_ehr_systems() -> None:
    from app.db_models import EHRSystem
    from sqlmodel import select
    
    with get_session() as session:
        # Check if already seeded
        existing = session.exec(select(EHRSystem)).first()
        if existing:
            return
            
        print("🚀 Seeding EHR Systems...")
        systems = [
            EHRSystem(name="Epic", status="Active"),
            EHRSystem(name="Cerner", status="Standby"),
            EHRSystem(name="Athena", status="Active"),
            EHRSystem(name="eClinicalWorks", status="Offline")
        ]
        for s in systems:
            session.add(s)
        session.commit()
        print("✅ EHR Systems seeded.")


def seed_clinic_data() -> None:
    from app.db_models import Clinic, User
    from sqlmodel import select
    from app.api.v1.auth import get_password_hash
    
    with get_session() as session:
        # Ensure Clinic exists
        clinic = session.exec(select(Clinic)).first()
        if not clinic:
            print("🚀 Seeding Clinic Data...")
            clinic = Clinic(
                name="Superhumanly Memorial Hospital",
                address="123 Clinical Way, Metropolis",
                contact_email="admin@superhumanly.ai"
            )
            session.add(clinic)
            session.flush()
        
        # Ensure Clinic Admin exists
        admin = session.exec(select(User).where(User.username == "clinic_admin")).first()
        if not admin:
            print("🚀 Seeding Clinic Admin...")
            admin = User(
                username="clinic_admin",
                email="clinic_admin@superhumanly.ai",
                hashed_password=get_password_hash("admin123"),
                role="clinic_admin",
                full_name="Hospital Director",
                clinic_id=clinic.id,
                is_active=True
            )
            session.add(admin)
            session.commit()
            print(f"✅ Clinic Admin seeded. ID: {admin.id}")
        else:
            # Ensure role is correct if it exists
            if admin.role != "clinic_admin":
                admin.role = "clinic_admin"
                session.add(admin)
                session.commit()
            print("✅ Clinic Admin Verified.")

def seed_fhir_data() -> None:
    from app.db_models import Customer, Encounter, HMSRecord
    from app.services import fhir_service
    from sqlmodel import select
    
    with get_session() as session:
        print("🚀 Migrating to FHIR-Native Data Models...")
        
        # 1. Customers to Patient Resources
        customers = session.exec(select(Customer).where(Customer.fhir_payload == None)).all()
        for c in customers:
            patient = fhir_service.map_customer_to_patient(c)
            c.fhir_payload = patient.dict()
            session.add(c)
            
        # 2. Encounters to Encounter Resources
        encounters = session.exec(select(Encounter).where(Encounter.fhir_payload == None)).all()
        for e in encounters:
            patient_obj = session.get(Customer, e.customer_id)
            fhir_encounter = fhir_service.map_encounter_to_fhir(e, patient=patient_obj)
            e.fhir_payload = fhir_encounter.dict()
            session.add(e)
            
        # 3. HMS Records (Sync simulation)
        hms_records = session.exec(select(HMSRecord).where(HMSRecord.fhir_payload == None)).all()
        for h in hms_records:
            encounter_obj = session.exec(select(Encounter).where(Encounter.customer_id == h.customer_id)).first()
            if encounter_obj:
                h.fhir_payload = encounter_obj.fhir_payload
                session.add(h)
                
        session.commit()
        print(f"✅ FHIR Data Migration Complete. Processed {len(customers)} Patients and {len(encounters)} Encounters.")

def apply_performance_indexes() -> None:
    """Creates GIN indexes for JSONB fields to optimize clinical aggregation."""
    from sqlalchemy import text
    with engine.connect() as conn:
        print("🚀 Applying High-Performance Clinical Indexes...")
        try:
            # GIN index for rx_json
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_encounter_rx_json_gin ON encounter USING GIN (rx_json)"))
            # GIN index for clinical_data
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_encounter_clinical_data_gin ON encounter USING GIN (clinical_data)"))
            conn.commit()
            print("✅ GIN Indexes applied successfully.")
        except Exception as e:
            print(f"⚠️ Warning: Could not apply GIN indexes (might not be PostgreSQL): {e}")


def get_session() -> Session:
    return Session(engine)


def commit_audit_log(session: Session, audit) -> None:
    """Write audit trail without failing the caller (important for SQLite dev)."""
    try:
        session.add(audit)
        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"⚠️ Audit log skipped: {exc}")

from app.core.context import get_clinic_id
from sqlmodel.sql.expression import Select, SelectOfScalar

def scoped_select(model_class) -> Select:
    """
    Returns a select statement for the given model class, 
    automatically filtered by the current clinic_id context.
    """
    clinic_id = get_clinic_id()
    stmt = select(model_class)
    
    # Only apply filter if clinic_id is set and model has clinic_id attribute
    if clinic_id and hasattr(model_class, "clinic_id"):
        stmt = stmt.where(model_class.clinic_id == clinic_id)
        
    return stmt

async def get_async_session() -> AsyncSession:
    """Get async database session for high-performance queries"""
    if async_session_maker is None:
        raise RuntimeError("Async database not configured")
    async with async_session_maker() as session:
        yield session

