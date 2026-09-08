import logging
from typing import Optional
from pathlib import Path
from pydantic import ValidationError
from app.schemas.rx_schema import Prescription
from app.utils.text_normalize import normalize_text
from app.core.config import settings
from app.services.llm_factory import get_chat_llm
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)


def _load_prompt() -> str:
    prompt_path = Path("app/core/prompts/rx_extraction.prompt")
    return prompt_path.read_text(encoding="utf-8")


def clean_transcript(transcript: str) -> str:
    return normalize_text(transcript)


async def extract_prescription(transcript: str) -> Prescription:
    """
    Extracts structured prescription data in a single high-speed call.
    """
    from app.services.llm_factory import get_utility_llm
    llm = get_utility_llm()
    
    template = _load_prompt() + "\n\nTRANSCRIPT:\n{transcript}"
    prompt_str = template.format(transcript=transcript)
    
    try:
        raw_response = await llm.ainvoke(prompt_str)
        content = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)
        
        import re
        import json
        # Strip markdown and noise
        content = re.sub(r'```json\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'```\s*', '', content)
        content = content.strip()
        
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            content = content[start:end+1]
        
        data = json.loads(content)
        return Prescription.model_validate(data)
    except Exception as e:
        logger.error(f"❌ Prescription extraction failed: {e}")
        return Prescription(
            diagnosis="Extraction failed",
            medicines=[],
            advice="Please review transcript manually.",
            follow_up=""
        )
