import logging
import re
import asyncio
from typing import Dict, Any, List
from app.services.llm_factory import get_utility_llm

logger = logging.getLogger(__name__)

async def process_chunk(llm: Any, chunk: str, chunk_index: int) -> str:
    """Processes a single chunk of transcript for medical cleanup."""
    prompt = f"""
    You are a Medical Transcription Editor. 
    Your task is to fix phonetic ASR (Speech-to-Text) errors in this segment of a clinical transcript.
    
    COMMON ASR ERRORS TO FIX:
    - "Parasite mall" -> "Paracetamol"
    - "A tour of staten" -> "Atorvastatin"
    - "Fairing eye tis" -> "Pharyngitis"
    - "Hyper tension" -> "Hypertension"
    - "Sugar" -> "Glucose" (in clinical context)
    - "Pressure" -> "Blood Pressure" (in clinical context)
    
    CRITICAL RULES:
    1. Resolve medical drug names and clinical terms correctly.
    2. Maintain the exact speaker intent and tone.
    3. Return ONLY the cleaned transcript segment. No preamble or conversational noise.
    
    RAW SEGMENT [{chunk_index}]:
    {chunk}
    """
    try:
        raw_response = await llm.ainvoke(prompt)
        cleaned = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)
        cleaned = cleaned.strip()
        # Remove common LLM prefixes
        cleaned = re.sub(r'^(Cleaned transcript:|Here is the cleaned transcript:)\s*', '', cleaned, flags=re.IGNORECASE)
        return cleaned
    except Exception as e:
        logger.error(f"❌ Chunk {chunk_index} cleanup failed: {e}")
        return chunk

async def cleanup_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    High-Speed Medical ASR Sanitizer (Task 59.4.1)
    Uses a single high-throughput LLM call to eliminate orchestration latency.
    """
    from app.core.config import settings

    transcript = state.get("transcript", "")
    if not transcript:
        return {"cleaned_text": ""}

    if not settings.clinical_enable_cleanup_node:
        return {"cleaned_text": transcript.strip()}

    # Use high-speed utility LLM (Gemini 2.5 Flash if configured, or Puter OpenAI)
    llm = get_utility_llm()
    
    prompt = f"""You are a Medical Transcription Editor. Fix phonetic ASR errors (e.g. 'parasite mall' -> 'paracetamol').
    Maintain speaker intent. Return ONLY the cleaned text.
    
    TRANSCRIPT:
    {transcript}"""
    
    try:
        # Single non-blocking call
        res = await llm.ainvoke(prompt)
        cleaned = res.content if hasattr(res, 'content') else str(res)
        return {"cleaned_text": cleaned.strip()}
    except Exception as e:
        logger.error(f"❌ Fast cleanup failed: {e}")
        return {"cleaned_text": transcript}
