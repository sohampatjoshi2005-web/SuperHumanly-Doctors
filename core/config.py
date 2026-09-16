from pydantic_settings import BaseSettings
from pydantic import Field, AliasChoices


class Settings(BaseSettings):
    # LLM
    llm_provider: str = Field(
        default="openai",
        alias="LLM_PROVIDER",
        description="LLM provider. Supported: openai, bedrock, google, groq.",
    )
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    api_base_url: str = Field(default="", alias="API_BASE_URL")
    
    # Puter
    puter_api_key: str = Field(default="", alias="PUTER_API_KEY")

    # Groq
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")

    # Gemini
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    # Bedrock (Claude, etc.)
    bedrock_region: str = Field(
        default="us-east-1",
        alias="BEDROCK_REGION",
        description="AWS region for the Bedrock Runtime endpoint (must match where you enabled model access).",
    )
    bedrock_model_id: str = Field(
        default="anthropic.claude-haiku-4-5-20251001-v1:0",
        alias="BEDROCK_MODEL_ID",
        description="Bedrock modelId or inference id (e.g., global.anthropic...).",
    )
    bedrock_provider: str = Field(
        default="anthropic",
        alias=AliasChoices("BEDROCK_PROVIDER", "BEDROCK_MODEL_PROVIDER"),
        description="Required when BEDROCK_MODEL_ID is an ARN (e.g., anthropic).",
    )

    # ASR
    asr_provider: str = Field(default="sarvam", alias="ASR_PROVIDER")
    sarvam_api_key: str = Field(default="", alias="SARVAM_API_KEY")
    sarvam_base_url: str = Field(default="https://api.sarvam.ai", alias="SARVAM_BASE_URL")
    sarvam_speech_model: str = Field(default="saaras:v3", alias="SARVAM_SPEECH_MODEL")
    sarvam_mode: str = Field(default="transcribe", alias="SARVAM_MODE")
    whisper_model: str = Field(default="large-v3", alias="WHISPER_MODEL")
    whisper_device: str = Field(default="cpu", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field(default="int8", alias="WHISPER_COMPUTE_TYPE")
    whisper_language: str = Field(default="en", alias="WHISPER_LANGUAGE")
    whisper_beam_size: int = Field(default=5, alias="WHISPER_BEAM_SIZE")
    whisper_best_of: int = Field(default=5, alias="WHISPER_BEST_OF")
    whisper_temperature: float = Field(default=0.0, alias="WHISPER_TEMPERATURE")
    asr_prompt: str = Field(
        default=(
            "You are transcribing a clinical encounter between a physician and patient. "
            "Preserve medical terminology, drug names, dosages, frequencies, routes, and durations exactly."
        ),
        alias="ASR_PROMPT",
    )
    openai_transcription_model: str = Field(
        default="gpt-4o-transcribe",
        alias="OPENAI_TRANSCRIPTION_MODEL",
    )
    medical_transcript_model: str = Field(
        default="gpt-4o-mini",
        alias="MEDICAL_TRANSCRIPT_MODEL",
    )
    medical_terminology_glossary: str = Field(
        default="",
        alias="MEDICAL_TERMINOLOGY_GLOSSARY",
        description="Comma-separated list of preferred medical terms/drug names to preserve during transcript correction.",
    )
    enable_medical_transcript_cleanup: bool = Field(
        default=True,
        alias="ENABLE_MEDICAL_TRANSCRIPT_CLEANUP",
    )
    # Clinical pipeline tuning (latency vs precision)
    clinical_unified_extraction: bool = Field(
        default=True,
        alias="CLINICAL_UNIFIED_EXTRACTION",
        description="Single structured LLM call for SOAP/Rx/billing (faster, one coherent context).",
    )
    clinical_enable_cleanup_node: bool = Field(
        default=False,
        alias="CLINICAL_ENABLE_CLEANUP_NODE",
        description="Separate ASR cleanup LLM pass. Off when unified extraction fixes ASR inline.",
    )
    clinical_enable_swarm: bool = Field(
        default=False,
        alias="CLINICAL_ENABLE_SWARM",
        description="Pharmacist/internist/consensus fan-in. Off until real agent LLMs are wired.",
    )
    clinical_async_verification: bool = Field(
        default=False,
        alias="CLINICAL_ASYNC_VERIFICATION",
        description="Run QA verification after encounter save (faster UI). Default sync preserves precision.",
    )
    assemblyai_api_key: str = Field(default="", alias="ASSEMBLYAI_API_KEY")

    # Email (Resend)
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_sender_email: str = Field(
        default="onboarding@resend.dev", 
        alias=AliasChoices("RESEND_SENDER_EMAIL", "BREVO_SENDER_EMAIL")
    )
    email_sender_name: str = Field(
        default="Superhumanly Doctors", 
        alias=AliasChoices("RESEND_SENDER_NAME", "BREVO_SENDER_NAME")
    )
    email_default_to: str = Field(
        default="", 
        alias=AliasChoices("RESEND_DEFAULT_TO_EMAIL", "BREVO_DEFAULT_TO_EMAIL")
    )

    # Database
    database_url: str = Field(
        default="sqlite:///./doctor_support.db",
        alias="DATABASE_URL",
        description="SQLAlchemy URL. Use Postgres locally, e.g. postgresql+psycopg2://user:pass@localhost:5432/doctor_support",
    )

    cors_allow_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,https://superhumanlymedical.io",
        alias="CORS_ALLOW_ORIGINS",
        description="Comma-separated list of allowed CORS origins.",
    )

    environment: str = Field(
        default="development",
        alias="ENVIRONMENT",
        description="Runtime environment: development, staging, or production.",
    )

    site_url: str = Field(
        default="",
        alias="SITE_URL",
        description="Canonical marketing origin (https + host, no path, no trailing slash).",
    )

    # Infrastructure
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    shared_storage_dir: str = Field(default="/tmp/superhumanly", alias="SHARED_STORAGE_DIR")
    
    # MongoDB & Auth
    mongodb_url: str = Field(
        default="mongodb://localhost:27017/doctor_support", 
        alias="MONGODB_URL",
        description="MongoDB connection string (e.g. mongodb+srv://...)"
    )
    jwt_secret: str = Field(default="dev-secret-key-please-change-in-prod", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60 * 24 * 7, alias="ACCESS_TOKEN_EXPIRE_MINUTES") # 1 week

    # Initial Admin Seeding
    initial_admin_username: str = Field(default="admin", alias="INITIAL_ADMIN_USERNAME")
    initial_admin_email: str = Field(default="admin@superhumanly.ai", alias="INITIAL_ADMIN_EMAIL")
    initial_admin_password: str = Field(default="admin123", alias="INITIAL_ADMIN_PASSWORD")
    
    # EHR & SMART
    fhir_base_url: str = Field(default="http://localhost:8000/v1/ehr", alias="FHIR_BASE_URL")
    smart_callback_path: str = Field(default="/v1/auth/smart/callback", alias="SMART_CALLBACK_PATH")
    smart_client_id: str = Field(default="superhumanly_client_id", alias="SMART_CLIENT_ID")
    smart_scope: str = Field(
        default="openid fhirUser patient/*.read launch", 
        alias="SMART_SCOPE"
    )
    session_secret_key: str = Field(default="super-secret-smart-key-2026", alias="SESSION_SECRET_KEY")

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "env_prefix": "" # Ensure no prefix is expected
    }

    def validate_settings(self):
        """
        Fail-fast check for critical production keys.
        """
        critical_keys = ["database_url", "redis_url", "shared_storage_dir", "fhir_base_url"]
        if self.environment.lower() == "production":
            critical_keys.append("site_url")
        
        if self.llm_provider == "groq":
            critical_keys.extend(["groq_api_key", "gemini_api_key"])
        elif self.llm_provider == "google":
            critical_keys.append("gemini_api_key")
        elif self.llm_provider == "openai":
            critical_keys.append("openai_api_key")
            
        missing = [k for k in critical_keys if not getattr(self, k, None)]
        if missing:
            print(f"❌ CRITICAL CONFIGURATION ERROR: Missing environment variables: {[k.upper() for k in missing]}")
            # In production, we should exit
            # import sys; sys.exit(1)
        else:
            print("✅ Configuration validated successfully.")


settings = Settings()
settings.validate_settings()
