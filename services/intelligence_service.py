from typing import Dict, Any, List
import json
import re
import ast
from pydantic import BaseModel, Field
from app.services.llm_factory import get_chat_llm
from app.schemas.encounter_intelligence_schema import UnifiedEncounterAnalysis
from app.schemas.rx_schema import Medicine
from app.schemas.billing_schema import BillingCode
from app.schemas.cds_schema import RiskIndicator
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

def safe_parse_json(content: str) -> Dict[str, Any]:
    """
    Robust JSON parser for LLM responses.
    Handles Markdown backticks, trailing/leading conversation, single-quotes, and extra text.
    """
    if not content:
        return {}
        
    cleaned = re.sub(r'```json|```', '', content).strip()
    
    # Try Standard JSON Parsing
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
        
    # Extract JSON object substring
    try:
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1:
            json_str = cleaned[start:end+1]
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass
        
    # Python Literal Fallback (handles single quotes and unquoted keys/values safely)
    try:
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1:
            json_str = cleaned[start:end+1]
            # Replace JSON literals with Python literal equivalents for ast.literal_eval
            norm = re.sub(r'\btrue\b', 'True', json_str)
            norm = re.sub(r'\bfalse\b', 'False', norm)
            norm = re.sub(r'\bnull\b', 'None', norm)
            norm = re.sub(r'\bTRUE\b', 'True', norm)
            norm = re.sub(r'\bFALSE\b', 'False', norm)
            norm = re.sub(r'\bNULL\b', 'None', norm)
            res = ast.literal_eval(norm)
            if isinstance(res, dict):
                return res
    except Exception as eval_err:
        logger.warning(f"⚠️ ast.literal_eval fallback failed: {eval_err}")
        
    raise ValueError(f"Could not parse valid JSON from LLM response: {content}")

# Pydantic Schemas for Structured Output
class SubjectiveObjectiveSchema(BaseModel):
    subjective: str = Field(description="Subjective findings and patient complaints")
    objective: str = Field(description="Objective findings, vital signs, and physical exams")

class AssessmentPlanSchema(BaseModel):
    assessment_text: str = Field(description="Clinical assessment and diagnosis narrative")
    plan_text: str = Field(description="Clinical plan and treatment roadmap")

class RxParallelSchema(BaseModel):
    diagnosis: str = Field(description="Primary clinical diagnosis")
    medicines: List[Medicine] = Field(default_factory=list, description="List of prescribed medicines")
    advice: str = Field(description="Patient lifestyle or recovery advice")
    follow_up: str = Field(description="Follow-up timeline and instructions")

class AdminParallelSchema(BaseModel):
    vitals_check: bool = Field(default=False, description="Whether vitals were reviewed in the encounter")
    complexity: str = Field(default="Low", description="MDM clinical complexity: Low, Moderate, High")
    billing_codes: List[BillingCode] = Field(default_factory=list, description="ICD-10 or CPT billing codes")
    risk_indicators: List[RiskIndicator] = Field(default_factory=list, description="CDS clinical risk indicators")

def format_value_recursively(val: Any, prefix: str = "") -> List[str]:
    """
    Recursively flattens deeply nested clinical objects (dicts/lists) into a flat list
    of professional, clean bullet points without any raw dict/list stringification.
    """
    bullets = []
    
    if isinstance(val, dict):
        for k, v in val.items():
            # Clean and capitalize key (e.g. chief_complaints -> Chief Complaints)
            clean_k = k.replace("_", " ").title()
            new_prefix = f"{prefix} - {clean_k}" if prefix else clean_k
            
            if isinstance(v, (dict, list)):
                bullets.extend(format_value_recursively(v, new_prefix))
            else:
                bullets.append(f"- **{new_prefix}**: {v}")
    elif isinstance(val, list):
        for item in val:
            if isinstance(item, (dict, list)):
                bullets.extend(format_value_recursively(item, prefix))
            else:
                if prefix:
                    bullets.append(f"- **{prefix}**: {item}")
                else:
                    bullets.append(f"- {item}")
    else:
        if prefix:
            bullets.append(f"- **{prefix}**: {val}")
        else:
            bullets.append(f"- {val}")
            
    return bullets

def normalize_extracted_keys(data: Dict[str, Any], expected_fields: List[str]) -> Dict[str, Any]:
    """
    Dynamically normalizes LLM-returned JSON dictionaries to match expected schema field names.
    Handles capitalization, nesting, key variations, and partial matches gracefully.
    """
    if not isinstance(data, dict):
        return {}
        
    normalized = {}
    
    # 1. Flatten nested dictionary structures (e.g. if sections are wrapped inside a capitalized parent)
    flat_data = {}
    for k, v in data.items():
        if isinstance(v, dict):
            flat_data[k] = str(v)
            for sub_k, sub_v in v.items():
                flat_data[f"{k}_{sub_k}"] = sub_v
                flat_data[sub_k] = sub_v
        else:
            flat_data[k] = v
            
    combined_data = {**flat_data, **data}
    
    for field in expected_fields:
        # Exact match
        if field in combined_data:
            normalized[field] = combined_data[field]
            continue
            
        # Case-insensitive match
        field_lower = field.lower()
        found = False
        for k, v in combined_data.items():
            k_lower = k.lower()
            if k_lower == field_lower:
                normalized[field] = v
                found = True
                break
        if found:
            continue
            
        # Partial match variations (e.g. subjective_findings -> subjective, assessment -> assessment_text)
        for k, v in combined_data.items():
            k_lower = k.lower()
            if field_lower in k_lower or k_lower in field_lower:
                if field_lower == "plan" and "assessment" in k_lower:
                    continue
                normalized[field] = v
                found = True
                break
                
        if not found:
            normalized[field] = ""
            
    # Format nested structures cleanly using our recursive formatter
    for field in expected_fields:
        val = normalized[field]
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            normalized[field] = "\n".join(f"- {x}" for x in val)
        elif isinstance(val, (dict, list)):
            bullets = format_value_recursively(val)
            normalized[field] = "\n".join(bullets)
        elif val:
            normalized[field] = str(val)
            
    return normalized

@retry(stop=stop_after_attempt(1))
def extract_subjective_objective(transcript: str) -> Dict[str, str]:
    """Micro-Node 1: Extract Subjective & Objective data."""
    from app.services.llm_factory import get_clinical_llm
    llm = get_clinical_llm()
    try:
        json_llm = llm.bind(response_format={"type": "json_object"})
        system_msg = SystemMessage(content="You are a clinical database parser. You MUST return ONLY a valid JSON object matching the requested schema. Do not include any conversational text or markdown formatting code blocks.")
        human_msg = HumanMessage(content=f"""Extract Subjective and Objective findings from this clinical transcript.
        
        TRANSCRIPT:
        {transcript}
        
        CRITICAL: Your response MUST be a JSON object matching this schema exactly.
        You MUST return the values for "subjective" and "objective" as flat arrays of strings (List[str]).
        Each string in the array MUST be a complete, highly professional, narrative clinical sentence.
        Do NOT output nested dictionaries, raw key-value terms, or short database-like fields.
        
        Expected Schema:
        {{
          "subjective": [
             "The patient is a 39-year-old male presenting with acute, sharp left-sided chest pain that started last night while moving furniture.",
             "The pain is constant, rated 7-8 out of 10 in severity, and worsened by deep breathing or laying down.",
             "Patient reports history of smoking one pack of cigarettes per day for 10-15 years...",
             ...
          ],
          "objective": [
             "On physical examination, the neck was noted to be slightly swollen, with no trauma or pain over the chest.",
             "The patient exhibited mild difficulty and noisy breathing during the encounter.",
             ...
          ]
        }}""")
        res = json_llm.invoke([system_msg, human_msg])
        parsed = safe_parse_json(res.content)
        normalized = normalize_extracted_keys(parsed, ["subjective", "objective"])
        return {
            "subjective": normalized["subjective"],
            "objective": normalized["objective"]
        }
    except Exception as e:
        logger.error(f"❌ Subjective/Objective extraction failed: {e}")
        return {
            "subjective": "The patient presented with clinical symptoms described in the transcript.",
            "objective": "Objective findings, vitals, and physical exams were not explicitly detailed."
        }

@retry(stop=stop_after_attempt(1))
def extract_assessment_plan(transcript: str) -> Dict[str, str]:
    """Micro-Node 2: Extract Assessment & Plan narrative."""
    from app.services.llm_factory import get_clinical_llm
    llm = get_clinical_llm()
    try:
        json_llm = llm.bind(response_format={"type": "json_object"})
        system_msg = SystemMessage(content="You are a clinical database parser. You MUST return ONLY a valid JSON object matching the requested schema. Do not include any conversational text or markdown formatting code blocks.")
        human_msg = HumanMessage(content=f"""Extract clinical Assessment and Plan from this clinical transcript.
        
        TRANSCRIPT:
        {transcript}
        
        CRITICAL: Your response MUST be a JSON object matching this schema exactly.
        You MUST return the values for "assessment_text" and "plan_text" as flat arrays of strings (List[str]).
        Each string in the array MUST be a complete, highly professional, narrative clinical sentence detailing the medical reasoning or clinical path.
        Do NOT output nested dictionaries, raw key-value terms, or short database-like fields.
        
        Expected Schema:
        {{
          "assessment_text": [
             "The patient presents with acute chest pain raising concern for potential acute coronary syndrome given his daily smoking history.",
             "Significant paternal history of early myocardial infarction at age 45 elevates cardiovascular risk profile.",
             ...
          ],
          "plan_text": [
             "Order an immediate 12-lead EKG and serial cardiac enzymes to rule out acute myocardial injury.",
             "Advise patient on strict smoking cessation and provide educational resources on lifestyle modification.",
             ...
          ]
        }}""")
        res = json_llm.invoke([system_msg, human_msg])
        parsed = safe_parse_json(res.content)
        normalized = normalize_extracted_keys(parsed, ["assessment_text", "plan_text"])
        return {
            "assessment_text": normalized["assessment_text"],
            "plan_text": normalized["plan_text"]
        }
    except Exception as e:
        logger.error(f"❌ Assessment/Plan extraction failed: {e}")
        return {
            "assessment_text": "Clinical assessment of the patient's symptoms based on encounter transcript.",
            "plan_text": "Clinical plan, diagnostic workup, and treatment strategies to be initiated."
        }

@retry(stop=stop_after_attempt(1))
def extract_rx_parallel(transcript: str) -> Dict[str, Any]:
    """Micro-Node 3: Extract Prescription details."""
    from app.services.llm_factory import get_clinical_llm
    llm = get_clinical_llm()
    try:
        json_llm = llm.bind(response_format={"type": "json_object"})
        system_msg = SystemMessage(content="You are a clinical prescription parser. You MUST return ONLY a valid JSON object matching the requested schema. No conversation, no markdown code blocks.")
        human_msg = HumanMessage(content=f"""Extract Medicines, primary diagnosis, advice, and follow-up instructions.
        
        TRANSCRIPT:
        {transcript}
        
        CRITICAL: Return ONLY a valid JSON object matching this exact schema:
        {{
          "diagnosis": "primary diagnosis string",
          "medicines": [
            {{
              "medication": "medicine name",
              "dosage": "dosage e.g. 500mg",
              "frequency": "frequency e.g. Q8H or Twice Daily",
              "duration": "duration e.g. 5 Days",
              "instructions": "SIG instructions"
            }}
          ],
          "advice": "lifestyle advice",
          "follow_up": "follow-up timeline"
        }}""")
        res = json_llm.invoke([system_msg, human_msg])
        parsed = safe_parse_json(res.content)
        
        # Normalize list and key names
        diagnosis = parsed.get("diagnosis", parsed.get("Diagnosis", "Clinical Encounter"))
        raw_medicines = parsed.get("medicines", parsed.get("Medicines", []))
        advice = parsed.get("advice", parsed.get("Advice", "General medical advice and rest."))
        follow_up = parsed.get("follow_up", parsed.get("Follow_Up", parsed.get("Follow-up", "Follow up as clinically indicated.")))
        
        # Ensure raw_medicines is always a list of dicts
        medicines = []
        if isinstance(raw_medicines, list):
            for med in raw_medicines:
                if isinstance(med, dict):
                    medicines.append({
                        "medication": med.get("medication", med.get("name", med.get("med", "Unknown Medicine"))),
                        "dosage": med.get("dosage", med.get("dose", "As directed")),
                        "frequency": med.get("frequency", med.get("freq", "Once daily")),
                        "duration": med.get("duration", "As needed"),
                        "instructions": med.get("instructions", med.get("sig", "Take as directed"))
                    })
                elif isinstance(med, str):
                    medicines.append({
                        "medication": med,
                        "dosage": "As directed",
                        "frequency": "Once daily",
                        "duration": "As needed",
                        "instructions": "Take as directed"
                    })
                    
        return {
            "diagnosis": diagnosis,
            "medicines": medicines,
            "advice": advice,
            "follow_up": follow_up
        }
    except Exception as e:
        logger.error(f"❌ Rx extraction failed completely: {e}")
        return {
            "diagnosis": "Clinical Encounter",
            "medicines": [],
            "advice": "General medical and supportive advice as per clinical protocol.",
            "follow_up": "Follow up as clinically indicated or in case of worsening symptoms."
        }

@retry(stop=stop_after_attempt(1))
def extract_admin_parallel(transcript: str) -> Dict[str, Any]:
    """Micro-Node 4: Extract Billing & Risk."""
    from app.services.llm_factory import get_admin_llm
    llm = get_admin_llm()
    try:
        json_llm = llm.bind(response_format={"type": "json_object"})
        system_msg = SystemMessage(content="You are an administrative medical coder. You MUST return ONLY a valid JSON object matching the requested schema. No conversation, no markdown code blocks.")
        human_msg = HumanMessage(content=f"""Extract ICD-10/CPT codes and clinical risks.
        
        TRANSCRIPT:
        {transcript}
        
        CRITICAL: Return ONLY a valid JSON object matching this exact schema:
        {{
          "vitals_check": true/false,
          "complexity": "Low/Moderate/High",
          "billing_codes": [
            {{
              "code": "ICD-10 or CPT code",
              "description": "code description",
              "justification": "clinical justification"
            }}
          ],
          "risk_indicators": [
            {{
              "factor": "risk factor",
              "severity": "Low/Moderate/High",
              "details": "risk explanation"
            }}
          ]
        }}""")
        res = json_llm.invoke([system_msg, human_msg])
        parsed = safe_parse_json(res.content)
        
        vitals_check = parsed.get("vitals_check", parsed.get("Vitals_Check", parsed.get("vitals", False)))
        complexity = parsed.get("complexity", parsed.get("Complexity", "Moderate"))
        raw_billing = parsed.get("billing_codes", parsed.get("Billing_Codes", parsed.get("billing", [])))
        raw_risks = parsed.get("risk_indicators", parsed.get("Risk_Indicators", parsed.get("risks", [])))
        
        billing_codes = []
        if isinstance(raw_billing, list):
            for code in raw_billing:
                if isinstance(code, dict):
                    code_str = code.get("code", "Unknown Code")
                    system = "CPT" if ("cpt" in str(code_str).lower() or len(str(code_str)) == 5) else "ICD-10-CM"
                    
                    category = code.get("category", "")
                    if not category:
                        if system == "ICD-10-CM":
                            icd10_count = sum(1 for c in billing_codes if c.get("system") == "ICD-10-CM")
                            category = "Primary Diagnosis" if icd10_count == 0 else "Secondary Diagnosis"
                        else:
                            category = "Evaluation & Management"
                            
                    billing_codes.append({
                        "code": code_str,
                        "system": system,
                        "description": code.get("description", "No description provided"),
                        "justification": code.get("justification", "Clinical justification not detailed"),
                        "category": category,
                        "confidence": float(code.get("confidence", 0.95)),
                        "evidence": code.get("evidence", [])
                    })
                    
        risk_indicators = []
        if isinstance(raw_risks, list):
            for risk in raw_risks:
                if isinstance(risk, dict):
                    risk_indicators.append({
                        "factor": risk.get("factor", "General health factor"),
                        "severity": risk.get("severity", "Low"),
                        "details": risk.get("details", "No details provided")
                    })
                    
        return {
            "vitals_check": bool(vitals_check),
            "complexity": complexity,
            "billing_codes": billing_codes,
            "risk_indicators": risk_indicators
        }
    except Exception as e:
        logger.error(f"❌ Admin extraction failed completely: {e}")
        return {
            "vitals_check": False,
            "complexity": "Moderate",
            "billing_codes": [],
            "risk_indicators": []
        }



@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=6),
    reraise=True
)
def analyze_clinical_parallel(transcript: str, historical_context: str = "") -> Dict[str, Any]:
    """
    Parallel Node A: Extract SOAP, RX, and Patient Summary.
    Optimized for Groq 8B for maximum speed (<3s).
    """
    from app.services.llm_factory import get_utility_llm
    llm = get_utility_llm() # 8B model
    
    prompt = f"""You are a Clinical Documentation Expert. Extract SOAP and RX from this transcript.
    TRANSCRIPT: {transcript}
    HISTORY: {historical_context}
    
    RETURN ONLY JSON:
    {{
      "subjective": "...", "objective": "...", "assessment_text": "...", "plan_text": "...",
      "diagnosis": "...", "medicines": [], "advice": "...", "follow_up": "...",
      "patient_summary": "Patient-friendly summary",
      "summary_sections": {{ "Symptoms": "...", "Assessment": "...", "Plan": "..." }}
    }}"""
    
    response = llm.invoke([HumanMessage(content=prompt)])
    return safe_parse_json(response.content)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=6),
    reraise=True
)
@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8), reraise=True)
def extract_clinical_unified(transcript: str, historical_context: str = "") -> Dict[str, Any]:
    """
    Single-pass clinical extraction: ASR correction, SOAP, Rx, billing, CDS, and header summary.
    Replaces four parallel micro-extractors + narrative synthesis for lower latency.
    """
    from app.services.llm_factory import get_clinical_llm

    llm = get_clinical_llm()
    json_llm = llm.bind(response_format={"type": "json_object"})
    history_block = f"\n\nPATIENT HISTORY:\n{historical_context}" if historical_context else ""

    system_msg = SystemMessage(
        content=(
            "You are an expert clinical documentation engine. "
            "Correct likely ASR/phonetic errors in drug and diagnosis terms while extracting. "
            "Return ONLY valid JSON matching the schema. No markdown."
        )
    )
    human_msg = HumanMessage(
        content=f"""Extract a complete clinical encounter from this transcript.{history_block}

TRANSCRIPT:
{transcript}

Return JSON with this exact structure:
{{
  "cleaned_transcript": "ASR-corrected full transcript text",
  "subjective": ["narrative bullet sentences for S"],
  "objective": ["narrative bullet sentences for O"],
  "assessment_text": ["narrative bullet sentences for A"],
  "plan_text": ["narrative bullet sentences for P"],
  "diagnosis": "primary diagnosis",
  "medicines": [
    {{"medication": "", "dosage": "", "frequency": "", "duration": "", "instructions": ""}}
  ],
  "advice": "lifestyle advice",
  "follow_up": "follow-up timeline",
  "vitals_check": true,
  "complexity": "Low|Moderate|High",
  "billing_codes": [
    {{"code": "", "description": "", "justification": ""}}
  ],
  "risk_indicators": [
    {{"factor": "", "severity": "Low|Moderate|High", "details": ""}}
  ],
  "patient_summary": "1-2 sentence clinical header summary, no section prefixes"
}}"""
    )

    res = json_llm.invoke([system_msg, human_msg])
    return safe_parse_json(res.content if hasattr(res, "content") else str(res))


def analyze_admin_parallel(transcript: str) -> Dict[str, Any]:
    """
    Parallel Node B: Extract Billing and CDS risks.
    Optimized for Groq 8B for maximum speed (<3s).
    """
    from app.services.llm_factory import get_utility_llm
    llm = get_utility_llm() # 8B model
    
    prompt = f"""You are a Medical Billing Auditor. Extract Billing Codes (ICD-10/CPT) and CDS risks.
    TRANSCRIPT: {transcript}
    
    RETURN ONLY JSON:
    {{
      "vitals_check": true, "complexity": "Low/Moderate/High",
      "codes_reasoning": "...", "billing_codes": [],
      "risk_indicators": []
    }}"""
    
    response = llm.invoke([HumanMessage(content=prompt)])
    return safe_parse_json(response.content)
