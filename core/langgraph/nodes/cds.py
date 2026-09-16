from typing import Any, Dict
from app.schemas.cds_schema import CDSAnalysis
from app.services.llm_factory import get_chat_llm
import logging

logger = logging.getLogger(__name__)

async def cds_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract clinical risk indicators in parallel using a single raw call.
    """
    cleaned_text = state.get("cleaned_text", "")
    if not cleaned_text:
        return {"cds": CDSAnalysis(risks=[], summary="No text to analyze.")}

    from app.services.llm_factory import get_utility_llm
    llm = get_utility_llm()

    prompt = f"""
    You are a clinical decision support AI. Analyze the following medical encounter transcript 
    and identify any high-risk clinical indicators. 
    You MUST return ONLY a valid JSON object. No conversational text.
    
    Expected JSON Structure:
    {{
      "risks": [
        {{ "type": "Sepsis", "severity": "High", "evidence": "...", "action_recommendation": "..." }}
      ],
      "summary": "Overall risk profile summary"
    }}
    
    Transcript:
    {cleaned_text}
    """
    
    try:
        raw_response = await llm.ainvoke(prompt)
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
        return {"cds": CDSAnalysis(**data)}
    except Exception as e:
        logger.error(f"❌ CDS extraction failed: {e}")
        return {"cds": CDSAnalysis(risks=[], summary=f"Error analyzing risks.")}
