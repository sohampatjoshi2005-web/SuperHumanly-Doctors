import logging
import json
import re
from typing import Dict, Any, List
from app.core.langgraph.state import RxState

logger = logging.getLogger(__name__)

async def verification_node(state: RxState) -> Dict[str, Any]:
    """
    Adversarial clinical auditor node.
    Cross-references SOAP notes and Billing against the raw transcript.
    Auto-corrects discrepancies to ensure ultra-accuracy.
    """
    cleaned_text = state.get("cleaned_text", "")
    soap = state.get("soap", {})
    billing = state.get("billing", {})
    
    if not cleaned_text or not soap:
        return {}

    from app.services.llm_factory import get_utility_llm
    llm = get_utility_llm()

    # We provide the raw transcript AND the extracted data for auditing
    prompt = f"""You are a Medical Quality Assurance Auditor. Verify the clinical documentation against the raw transcript.
    
    RAW TRANSCRIPT:
    {cleaned_text}
    
    SOAP NOTES:
    {json.dumps(soap)}
    
    BILLING:
    {json.dumps(billing)}
    
    AUDIT RULES:
    1. Identify medications mentioned in the transcript but MISSING from the SOAP Plan.
    2. Identify symptoms/history mentioned but MISSING from the Subjective.
    3. Identify "invented" facts not present in the transcript.
    4. MDM AUDIT: Verify complexity against 2024 CMS criteria (Rx Management triggers Moderate).
    5. Zero-Unspecified: Ensure NO "unspecified" descriptors in billing.
    
    Return ONLY a JSON object matching this schema exactly:
    {{
      "audit_logs": ["List of identified corrections"],
      "soap": {{ ... updated soap object ... }},
      "billing": {{ ... updated billing object ... }}
    }}"""
    
    def safe_parse(content: str) -> Dict[str, Any]:
        # Strip markdown and noise
        content = re.sub(r'```json\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'```\s*', '', content)
        content = content.strip()
        
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            content = content[start:end+1]
        
        return json.loads(content)

    try:
        raw_response = await llm.ainvoke(prompt, response_format={"type": "json_object"})
        content = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)
        
        try:
            correction_data = json.loads(content.strip())
        except Exception:
            correction_data = safe_parse(content)
        
        # Log identified issues
        audit_logs = correction_data.get("audit_logs", [])
        if audit_logs:
            for log in audit_logs:
                logger.warning(f"🔍 Auditor Correction: {log}")
        
        return {
            "soap": correction_data.get("soap", soap),
            "billing": correction_data.get("billing", billing),
            "verification_audit": audit_logs
        }
        
    except Exception as e:
        logger.error(f"❌ Verification node failed: {e}")
        return {"verification_audit": [f"Verification failed: {str(e)}"]}
