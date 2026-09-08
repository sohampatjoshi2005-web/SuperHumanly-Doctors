<!-- GSD:project-start source:PROJECT.md -->
## Project

**Superhumanly Doctors**

Superhumanly Doctors is a B2B AI-powered clinical intelligence platform. It enables physicians to automate clinical documentation through high-fidelity audio transcription and structured prescription extraction, helping them focus more on patient care and less on paperwork.

**Core Value:** The core value is providing physicians with a "technical sovereign" assistant that converts raw clinical conversations into accurate, actionable medical summaries and prescriptions with zero manual data entry.

### Constraints

- **Security**: Must maintain HIPAA compliance standards for clinical data even during trial.
- **Database**: Must leverage the existing SQLModel/Beanie architecture for usage tracking.
- **Frontend**: Must maintain the existing premium, high-fidelity design system.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Language & Runtime
| Property | Value |
|----------|-------|
| Language | Python 3.14+ |
| Runtime | CPython |
| Package Manager | pip (requirements.txt) |
| Virtual Environment | `.venv/` |
## Core Framework
- **FastAPI** (`>=0.110.0`) — async web framework, entry point at `app/main.py`
- **Uvicorn** (`>=0.25.0`) — ASGI server
- **Pydantic** (`>=2.7.0`) — data validation and settings management
- **Pydantic-Settings** (`>=2.2.1`) — environment-based configuration via `app/core/config.py`
## AI / ML Stack
| Library | Version | Purpose |
|---------|---------|---------|
| LangChain | `>=0.2.0` | LLM orchestration layer |
| LangChain-Core | `>=0.2.0` | Base abstractions (messages, prompts) |
| LangChain-OpenAI | `>=0.1.0` | OpenAI / Ollama ChatLLM integration |
| LangChain-AWS | `>=0.2.0` | AWS Bedrock (Claude) integration |
| LangGraph | `>=0.1.0` | Multi-step agentic graph pipeline |
| faster-whisper | `>=1.0.3` | Local ASR transcription (preferred) |
| AssemblyAI | `>=0.30.0` | Cloud ASR alternative |
## Databases
| Database | Driver | Usage |
|----------|--------|-------|
| PostgreSQL | `psycopg2-binary` (`>=2.9.9`) | Primary relational store (Customers, Encounters) via SQLModel |
| SQLite | built-in | Local dev fallback (`doctor_support.db`) |
| MongoDB | `motor` (`>=3.3.2`) + `beanie` (`>=1.25.0`) | Users, TrialRequests, AuditLogs, Clinics (document store) |
| Redis | `redis` (`>=5.0.0`) | Audit log batching queue |
## Task Queue
- **Celery** (`>=5.3.0`) — background task processing
- Worker at `app/workers/audit_worker.py` flushes audit logs every 5 seconds
## ORM / ODM
- **SQLModel** (`>=0.0.22`) — SQL ORM for relational models (built on SQLAlchemy + Pydantic)
- **Beanie** (`>=1.25.0`) — async MongoDB ODM for document models
- **SQLAlchemy** async support via `asyncpg` / `aiosqlite`
## Email
- **Brevo (Sendinblue)** — transactional email via `sib-api-v3-sdk` (`>=7.6.0`)
## HTTP Client
- **httpx** (`>=0.27.0`) — async HTTP client for OpenAI transcription API calls
## Additional Utilities
- `python-multipart` (`>=0.0.9`) — file upload parsing for FastAPI
- `python-jose[cryptography]` (`>=3.3.0`) — JWT token creation/verification
- `passlib[bcrypt]` (`>=1.7.4`) — password hashing (bcrypt)
- `email-validator` (`>=2.0.0`) — Pydantic EmailStr validation
- `certifi` — TLS certificate verification for MongoDB Atlas
## Alternative Frontend
- **Streamlit** (`>=1.33.0`) — standalone admin/demo UI at `streamlit_app.py`
## Configuration
- `.env` file loaded automatically
- Key settings: `LLM_PROVIDER`, `ASR_PROVIDER`, `DATABASE_URL`, `MONGODB_URL`, `JWT_SECRET`, `BREVO_API_KEY`
- Supports OpenAI, Ollama, and AWS Bedrock LLM providers
- Supports Sarvam (cloud primary), Whisper (local fallback), OpenAI (cloud), and AssemblyAI ASR providers
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Language Style
- **Python 3.14+** with type hints throughout
- `from __future__ import annotations` used in some modules for forward references
- Pydantic v2 models with `Field()` descriptors for all schemas
## Code Organization
### API Routes
- Grouped by domain in `app/api/v1/`
- Each file defines a single `router = APIRouter(prefix=..., tags=[...])`
- Auth dependency injection via `Depends(get_current_user)` or `Depends(get_current_admin)`
- Request/Response models defined inline with routes (Pydantic `BaseModel`)
### Services
- Pure functions or classes in `app/services/`
- No direct database access in API routes — delegated to services
- Service functions accept primitives, return domain objects
### Models
- **SQLModel** for relational tables (`app/db_models.py`)
- **Beanie Documents** for MongoDB collections (`app/models/*.py`)
- UUID-based primary keys (string format) for SQL models
- Timestamp fields default to `datetime.now(timezone.utc)` or `datetime.utcnow()`
## Error Handling
- FastAPI `HTTPException` for API errors with specific status codes
- Try/except with fallback patterns in services (e.g., `audit_service.py` falls back from Redis to MongoDB)
- `RuntimeError` for configuration errors (missing API keys)
- LLM extraction uses structured output with Pydantic fallback parser
## Authentication Pattern
- OAuth2 Bearer token via `OAuth2PasswordBearer`
- `get_current_user()` — async dependency that decodes JWT and fetches User from MongoDB
- `get_current_admin()` — wraps `get_current_user()` with role check
- Password hashing with bcrypt (`passlib`)
## Configuration Pattern
- Single `Settings` class extending `BaseSettings` in `app/core/config.py`
- All config via environment variables with sensible defaults
- `Field(alias="ENV_VAR_NAME")` for env-to-attribute mapping
- `.env` file auto-loaded
## Dependency Injection
- FastAPI `Depends()` for authentication and database sessions
- Database sessions via generator functions (`get_session()`, `get_async_session()`)
## Logging
- Emoji-prefixed status messages in startup/seeding: `🚀`, `✓`, `⚠️`, `✅`
- Python `logging` module used in audit service
- Print statements for startup diagnostics (should migrate to logging)
## Import Style
- Absolute imports from `app.*` package
- Lazy imports for optional dependencies (e.g., `from faster_whisper import WhisperModel` inside function)
- Type imports from `typing` module
## Async/Sync Mix
- API routes are async (`async def`)
- SQLModel operations are synchronous (via `get_session()`)
- MongoDB operations are async (via Beanie)
- `run_in_threadpool()` used to offload CPU-heavy LangGraph invocations
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern
```
```
## Layers
### 1. API Layer (`app/api/v1/`)
| Router | Prefix | Auth | Purpose |
|--------|--------|------|---------|
| `auth.py` | `/v1/auth` | Public (register/login), Bearer (me) | User registration, login, JWT tokens |
| `process.py` | `/v1/process-audio` | Bearer | Audio upload → LangGraph pipeline |
| `process_text.py` | `/v1/process-text` | Bearer | Text transcript → LangGraph pipeline |
| `customers.py` | `/v1/customers` | Bearer | Patient/customer CRUD |
| `encounters.py` | `/v1/encounters` | Bearer | Clinical encounter history |
| `trials.py` | `/v1/trial` | Public | Trial request submission |
| `admin.py` | `/v1/admin` | Admin role | Admin stats, trial management |
| `secure_share.py` | `/v1/share` | Bearer (generate), Public (view) | Time-limited encounter sharing via JWT |
### 2. LangGraph Pipeline (`app/core/langgraph/`)
```
```
- `audio_path` → `transcript` → `cleaned_text` → `rx` (Prescription) → `rx_text`
- Optional email fields: `to_email`, `email_subject`, `email_status`
- `transcription.py` — ASR via configured provider
- `cleanup.py` — Medical transcript correction via LLM
- `extraction.py` — Structured prescription extraction (LLM with Pydantic schema binding)
- `validation.py` — Prescription field validation
- `formatting.py` — Human-readable prescription text
- `email.py` — Optional email dispatch via Brevo
### 3. Service Layer (`app/services/`)
| Service | File | Purpose |
|---------|------|---------|
| `transcription_service.py` | Multi-provider ASR with medical cleanup | Core |
| `llm_factory.py` | LLM provider abstraction (OpenAI/Bedrock) | Core |
| `rx_service.py` | Prescription extraction with structured output | Core |
| `summary_service.py` | Patient summary generation | Core |
| `formatting_service.py` | Prescription text formatting | Core |
| `email_service.py` | Brevo transactional email | Supporting |
| `audit_service.py` | Redis-batched audit logging | Supporting |
| `storage_service.py` | SQLModel CRUD for Customers/Encounters | Data |
### 4. Data Layer
- **PostgreSQL/SQLite** (via SQLModel): Relational data — `Customer`, `Encounter`
- **MongoDB** (via Beanie): Document data — `User`, `TrialRequest`, `AuditLog`, `Clinic`
### 5. Background Workers (`app/workers/`)
- **Celery** worker: `audit_worker.py` flushes Redis audit queue to MongoDB every 5 seconds
## Data Flow
### Audio Processing (Primary Flow)
```
```
### Authentication Flow
```
```
## Entry Points
| Entry Point | Command | Purpose |
|-------------|---------|---------|
| FastAPI API | `uvicorn app.main:app` | Production API server |
| Streamlit UI | `streamlit run streamlit_app.py` | Demo/admin interface |
| Celery Worker | `celery -A app.workers.audit_worker worker` | Background audit flushing |
## Key Design Decisions
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
