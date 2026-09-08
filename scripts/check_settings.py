import os
from dotenv import load_dotenv
from app.core.config import settings

def check_settings():
    load_dotenv()
    print(f"CORS_ALLOW_ORIGINS: {settings.cors_allow_origins}")
    print(f"DATABASE_URL: {settings.database_url}")
    print(f"LLM_PROVIDER: {settings.llm_provider}")

if __name__ == "__main__":
    check_settings()
