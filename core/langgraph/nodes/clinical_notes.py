from typing import Any, Dict
from app.services.llm_factory import get_chat_llm
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class SOAPAnalysis(BaseModel):
    subjective: str = Field(description="Patient's history and symptoms")
    objective: str = Field(description="Physical exam and vitals")
    assessment: str = Field(description="Clinical diagnosis and reasoning")
    plan: str = Field(description="Treatment strategy")
    summary_sections: Dict[str, str] = Field(description="Key highlights for UI: Symptoms, Assessment, Plan, Red Flags")
    patient_summary: str = Field(description="Friendly summary for the patient")

async def clinical_notes_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract SOAP notes and UI summaries in parallel using a single raw call.
    """
    cleaned_text = state.get("cleaned_text", "")
    if not cleaned_text:
        return {"soap": {}, "summary_sections": {}, "patient_summary": ""}

    from app.services.llm_factory import get_utility_llm
    llm = get_utility_llm()

    prompt = f"""
    Analyze the following clinical transcript and extract structured SOAP notes and summaries.
    You MUST return ONLY a valid JSON object. No conversational text.
    
    CRITICAL: Use a professional bulleted list format (using '-') for every section below. 
    Do NOT return plain paragraphs.
    
    Required Keys:
    - subjective: Patient's history and symptoms (bulleted)
    - objective: Physical exam and vitals (bulleted)
    - assessment: Clinical diagnosis and reasoning (bulleted)
    - plan: Treatment strategy (bulleted)
    - summary_sections: {{ "Symptoms": "...", "Assessment": "...", "Plan": "...", "Red Flags": "..." }}
    - patient_summary: Friendly summary for the patient (narrative style, STRICTLY 1-2 lines only)
    
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
        
        def to_str(val, bulleted=True):
            if val is None:
                return ""
                
            if isinstance(val, dict):
                # Flatten dictionary into bulleted string lines
                lines = []
                for k, v in val.items():
                    key_title = k.replace('_', ' ').title()
                    if isinstance(v, list):
                        v_str = ", ".join(str(i) for i in v)
                        lines.append(f"- **{key_title}**: {v_str}")
                    elif isinstance(v, dict):
                        nested = ", ".join(f"{nk.title()}: {nv}" for nk, nv in v.items())
                        lines.append(f"- **{key_title}**: {nested}")
                    else:
                        lines.append(f"- **{key_title}**: {v}")
                return "\n".join(lines)
                
            if isinstance(val, list):
                return "\n".join(f"- {str(i)}" for i in val)
            
            # If it's a string, ensure every line starts with a bullet if requested
            text_val = str(val).strip()
            if not text_val:
                return ""
            
            if not bulleted:
                return text_val
                
            # Split by newlines OR literal bullet patterns to ensure individual dots
            import re
            # Split by \n, or a dash/bullet at the start of a line or after a space
            raw_lines = re.split(r'\n|(?<=\s)[-•·\*](?=\s)|(?<=^)[-•·\*](?=\s)', text_val)
            
            bulleted_lines = []
            for line in raw_lines:
                line = line.strip()
                if not line:
                    continue
                # Clean the line of any leading bullet noise
                clean_line = re.sub(r'^[-•·\*]+\s*', '', line).strip()
                if clean_line:
                    bulleted_lines.append(f"- {clean_line}")
            
            return "\n".join(bulleted_lines)

        return {
            "soap": {
                "subjective": to_str(data.get("subjective")),
                "objective": to_str(data.get("objective")),
                "assessment": to_str(data.get("assessment")),
                "plan": to_str(data.get("plan"))
            },
            "summary_sections": {k: to_str(v) for k, v in data.get("summary_sections", {}).items()},
            "patient_summary": to_str(data.get("patient_summary"), bulleted=False)
        }
    except Exception as e:
        logger.error(f"❌ Clinical notes extraction failed: {e}")
        return {"soap": {}, "summary_sections": {}, "patient_summary": "Error generating notes."}
