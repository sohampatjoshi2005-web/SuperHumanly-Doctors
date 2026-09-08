from pathlib import Path
from langchain_core.prompts import PromptTemplate
from app.services.llm_factory import get_chat_llm
from app.schemas.billing_schema import BillingAnalysis


def _load_prompt() -> str:
    prompt_path = Path("app/core/prompts/billing_extraction.prompt")
    return prompt_path.read_text(encoding="utf-8")


import logging

logger = logging.getLogger(__name__)

async def extract_billing_info(transcript: str) -> BillingAnalysis:
    """
    Extracts ICD-10, CPT, and Complexity info in a single high-speed call.
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
        return BillingAnalysis.model_validate(data)
    except Exception as e:
        logger.error(f"❌ Billing extraction failed: {e}")
        return BillingAnalysis(
            vitals_check=False,
            complexity="Low",
            codes_reasoning="Extraction failed.",
            codes=[]
        )
