from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.api.v1.process import router as process_router
from app.api.v1.process_text import router as process_text_router
from app.api.v1.customers import router as customers_router
from app.api.v1.encounters import router as encounters_router
from app.api.v1.auth import router as auth_router, seed_initial_admin
from app.api.v1.streaming import router as streaming_router
from app.api.v1.trials import router as trials_router
from app.api.v1.admin import router as admin_router
from app.api.v1.secure_share import router as secure_share_router
from app.api.v1.upgrade import router as upgrade_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.agents import router as agents_router
from app.api.v1.ehr import router as ehr_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.clinic_admin import router as clinic_admin_router
from app.api.v1.smart_auth import router as smart_auth_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.referrals import router as referrals_router
from app.api.v1.wellness import router as wellness_router
from app.api.seo_crawl import router as seo_crawl_router
from app.api.v1.seo import router as seo_router
from app.db import init_db, seed_ehr_systems, seed_clinic_data
from app.core.config import settings
from app.services.audit_service import init_redis
from app.middleware.seo_headers import ApiNoIndexMiddleware

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup sequence
    init_db()
    seed_ehr_systems()
    seed_clinic_data()
    from app.db import seed_fhir_data, apply_performance_indexes
    seed_fhir_data()
    apply_performance_indexes()
    # Initialize Redis for audit logging batching
    init_redis()
    await seed_initial_admin()
    yield
    # Shutdown sequence (if any)
    pass

def create_app() -> FastAPI:
  is_production = settings.environment.lower() == "production"
  application = FastAPI(
      title="Doctor Support Agentic System",
      lifespan=lifespan,
      docs_url=None if is_production else "/docs",
      redoc_url=None if is_production else "/redoc",
      openapi_url=None if is_production else "/openapi.json",
  )

  origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
  application.add_middleware(
      CORSMiddleware,
      allow_origins=origins,
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  application.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
  application.add_middleware(ApiNoIndexMiddleware)

  application.include_router(auth_router, prefix="/v1")
  application.include_router(trials_router, prefix="/v1")
  application.include_router(admin_router, prefix="/v1")
  application.include_router(secure_share_router, prefix="/v1")
  application.include_router(process_router, prefix="/v1")
  application.include_router(process_text_router, prefix="/v1")
  application.include_router(streaming_router, prefix="/v1")
  application.include_router(customers_router, prefix="/v1")
  application.include_router(encounters_router, prefix="/v1")
  application.include_router(upgrade_router, prefix="/v1")
  application.include_router(intelligence_router, prefix="/v1")
  application.include_router(agents_router, prefix="/v1")
  application.include_router(ehr_router, prefix="/v1")
  application.include_router(tasks_router, prefix="/v1")
  application.include_router(clinic_admin_router, prefix="/v1")
  application.include_router(smart_auth_router, prefix="/v1")
  application.include_router(analytics_router, prefix="/v1")
  application.include_router(referrals_router, prefix="/v1")
  application.include_router(wellness_router, prefix="/v1")
  application.include_router(seo_router, prefix="/v1")
  application.include_router(seo_crawl_router)

  @application.get("/health")
  async def health_check():
    """
    Consolidated health check for container orchestration and monitoring.
    """
    from app.db import engine
    from app.services.audit_service import redis_client
    from sqlalchemy import text
    
    health = {"status": "healthy", "dependencies": {}}
    
    # 1. DB Health
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health["dependencies"]["database"] = "connected"
    except Exception as e:
        health["status"] = "degraded"
        health["dependencies"]["database"] = f"error: {str(e)}"
        
    # 2. Redis Health
    try:
        if redis_client and redis_client.ping():
            health["dependencies"]["redis"] = "connected"
        else:
            health["dependencies"]["redis"] = "disconnected"
    except Exception:
        health["dependencies"]["redis"] = "error"
        health["status"] = "degraded"
        
    # 3. FHIR Connectivity
    try:
        import httpx
        metadata_url = f"{settings.fhir_base_url.rstrip('/')}/metadata"
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(metadata_url)
            if resp.status_code == 200:
                health["dependencies"]["fhir_server"] = "reachable"
            else:
                health["dependencies"]["fhir_server"] = f"unhealthy (status: {resp.status_code})"
                health["status"] = "degraded"
    except Exception as e:
        health["dependencies"]["fhir_server"] = f"unreachable: {str(e)}"
        health["status"] = "degraded"
        
    return health

  return application


app = create_app()
