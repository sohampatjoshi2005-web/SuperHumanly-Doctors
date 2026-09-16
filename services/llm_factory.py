from typing import Optional, List, Any
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_aws import ChatBedrock
from langchain_core.messages import BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def get_chat_llm(provider: Optional[str] = None, model: Optional[str] = None, temperature: float = 0.0) -> BaseChatModel:
    """
    Factory function to get a ChatLLM based on configuration.
    """
    provider = (provider or settings.llm_provider or "openai").strip().lower()
    
    if provider == "openai":
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.api_base_url if settings.api_base_url else None,
            model=model or settings.openai_model,
            temperature=temperature,
            timeout=60.0,
            max_retries=0
        )
    
    elif provider == "groq":
        # Note: 70B has higher TPM limits (30k) than 8B (6k) on Free Tier
        return ChatGroq(
            api_key=settings.groq_api_key,
            model_name=model or "llama-3.3-70b-versatile",
            temperature=temperature,
            timeout=60.0,
            max_retries=0
        )

    elif provider == "google":
        return ChatGoogleGenerativeAI(
            google_api_key=settings.gemini_api_key,
            model=model or settings.gemini_model,
            temperature=temperature,
            timeout=60.0,
            max_retries=0
        )
        
    else:
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.api_base_url if settings.api_base_url else None,
            model="gpt-4o-mini",
            timeout=60.0,
            max_retries=0
        )

def get_clinical_llm():
    """Uses Puter OpenAI exclusively as per USER instructions."""
    return get_chat_llm(provider="openai")

def get_admin_llm():
    """Uses Puter OpenAI exclusively as per USER instructions."""
    return get_chat_llm(provider="openai")

def get_utility_llm():
    """Uses Puter OpenAI exclusively as per USER instructions to avoid daily free-tier quota limits."""
    return get_chat_llm(provider="openai")
