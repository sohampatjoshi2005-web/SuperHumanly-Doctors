import asyncio
from app.db import get_async_session
from app.services.reconciliation_service import reconcile_usage_meters
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from app.models.user import User
from app.models.audit import AuditLog
from app.core.config import settings

async def run_recon():
    # Init Beanie (since this is a standalone script)
    client = AsyncIOMotorClient(settings.mongodb_url)
    try:
        await init_beanie(database=client.get_database("doctor_support"), document_models=[User, AuditLog])
        print("Connected to MongoDB")
    except Exception as e:
        print(f"❌ MongoDB not available: {e}")
        return

    async for session in get_async_session():
        result = await reconcile_usage_meters(session)
        print(f"Reconciliation Result: {result}")

if __name__ == "__main__":
    asyncio.run(run_recon())
