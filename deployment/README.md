# Production Deployment Playbook

This playbook documents the steps to deploy the **Superhumanly Doctors** platform in production-grade cloud environments, ensuring high availability, compliance, and optimal performance.

---

## 🏗️ 1. Architecture Topology

A production deployment consists of five containerized services running under an orchestration layer (e.g., AWS ECS, Kubernetes, or Docker Swarm):

```mermaid
graph TD
    subgraph "External Cloud Services"
        OpenAI[OpenAI / Bedrock API]
        Brevo[Brevo Transactional Email]
        Atlas[(MongoDB Atlas)]
    end

    subgraph "Private Virtual Cloud (VPC)"
        Nginx[Nginx Reverse Proxy]
        React[Frontend Nginx Container]
        FastAPI[FastAPI ASGI Container]
        Worker[Celery ASR Worker]
        Redis[(Redis Cache & Queue)]
        Postgres[(PostgreSQL Relational DB)]
    end

    Internet((Public Internet)) --> Nginx
    Nginx --> React
    Nginx --> FastAPI
    FastAPI --> Redis
    FastAPI --> Postgres
    Worker --> Redis
    Worker --> Postgres
    FastAPI --> OpenAI
    FastAPI --> Atlas
    Worker --> Brevo
```

---

## 🔒 2. Configuration & Environment Variables

All services are configured using environment variables. Below is the production `.env` template:

### Relational & Document Stores
```env
# Relational Database URL (Postgres with asyncpg driver)
DATABASE_URL=postgresql+asyncpg://db_user:secure_password@postgres-endpoint:5432/superhumanly_prod

# MongoDB Connection String (Atlas preferred for production)
MONGODB_URL=mongodb+srv://atlas_user:atlas_password@cluster0.mongodb.net/superhumanly_prod?retryWrites=true&w=majority
```

### Security & Encryption
```env
# Cryptographic key for signing session tokens and sharing links
JWT_SECRET=super-secure-high-entropy-random-string-64-bytes-long
SESSION_SECRET_KEY=session-signing-secret-key-32-bytes

# CORS configuration (restrict to official institutional domains)
CORS_ALLOW_ORIGINS=https://portal.superhumanly.ai,https://admin.superhumanly.ai
```

### AI Pipeline Configuration
```env
# LLM Provider selection (options: openai, bedrock)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# AWS Bedrock settings (if LLM_PROVIDER=bedrock)
AWS_ACCESS_KEY_ID=AKIAxxxxxxxxxxxxxxxx
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_REGION=us-east-1

# Speech-to-Text Provider (options: whisper, sarvam, assemblyai)
ASR_PROVIDER=assemblyai
ASSEMBLYAI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Transactional Email (Brevo)
```env
BREVO_API_KEY=xkeysib-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SENDER_EMAIL=notifications@superhumanly.ai
SENDER_NAME="Superhumanly Notifications"
```

---

## 📦 3. Container Orchestration (Docker Compose)

For localized deployment or private VPS hosting, use the multi-container configuration below.

Create a production `docker-compose.prod.yml`:
```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    container_name: superhumanly-prod-db
    environment:
      POSTGRES_USER: db_user
      POSTGRES_PASSWORD: secure_password
      POSTGRES_DB: superhumanly_prod
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: always

  redis:
    image: redis:7-alpine
    container_name: superhumanly-prod-redis
    ports:
      - "6379:6379"
    restart: always

  backend:
    image: superhumanly-backend:latest
    container_name: superhumanly-prod-backend
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql+psycopg2://db_user:secure_password@db:5432/superhumanly_prod
      - MONGODB_URL=mongodb://mongo-endpoint:27017/superhumanly_prod
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET=super-secure-key
    depends_on:
      - db
      - redis
    ports:
      - "8000:8000"
    restart: always

  worker:
    image: superhumanly-worker:latest
    container_name: superhumanly-prod-worker
    build:
      context: ./backend
      dockerfile: Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql+psycopg2://db_user:secure_password@db:5432/superhumanly_prod
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    restart: always

  frontend:
    image: superhumanly-frontend:latest
    container_name: superhumanly-prod-frontend
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "80:80"
    restart: always

volumes:
  pgdata:
```

---

## 🛡️ 4. Security & HIPAA Hardening Checklist

Before marking the environment as active for external clinicians, verify compliance with the following checklists:

- [ ] **Data Encryption at Rest**: Enable AWS KMS or dm-crypt on PostgreSQL and Redis data volumes.
- [ ] **Data Encryption in Transit**: Enforce SSL on PostgreSQL (`sslmode=require`) and MongoDB connections. Configure Nginx to reject all non-HTTPS requests.
- [ ] **Secret Management**: Never write secrets to `.env` in the codebase repository. Inject secrets dynamically at container launch using AWS Secrets Manager or HashiCorp Vault.
- [ ] **VPC Isolation**: Place PostgreSQL, MongoDB, and Redis in isolated private subnets. Only Nginx and the FastAPI API gateway should expose public ports.
- [ ] **Session Expiry**: Set JWT tokens to expire within 15 minutes, requiring automated background silent refresh. Enforce 1-hour expiry on secure shared clinical records.
