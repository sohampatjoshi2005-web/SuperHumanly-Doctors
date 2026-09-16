from typing import Dict, Any, List
import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)


def ensure_bulleted_lines(text: str) -> str:
    """
    Robust utility to convert plain text paragraphs or malformed lists into standard,
    highly readable Markdown bulleted lists. Every sentence or item is normalized to start with '- '.
    """
    if not text:
        return ""

    if isinstance(text, list):
        lines = []
        for item in text:
            item_str = str(item).strip()
            if not item_str:
                continue
            clean = re.sub(r'^[-*•·\d.]+\s*', '', item_str).strip()
            if clean:
                lines.append(f"- {clean}")
        return "\n".join(lines)

    text = str(text).strip()
    lines = text.split("\n")
    has_bullets = any(line.strip().startswith(("-", "*", "•", "·")) for line in lines if line.strip())

    if has_bullets:
        bulleted_lines = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            clean_line = re.sub(r'^[-*•·\d.]+\s*', '', line_str).strip()
            if clean_line:
                bulleted_lines.append(f"- {clean_line}")
        return "\n".join(bulleted_lines)

    sentences = re.split(r'\.(?=\s|$)', text)
    bulleted_lines = []
    for sent in sentences:
        sent_str = sent.strip()
        if not sent_str:
            continue
        clean_sent = re.sub(r'^[-*•·\d.]+\s*', '', sent_str).strip()
        if clean_sent:
            bulleted_lines.append(f"- {clean_sent}.")
    return "\n".join(bulleted_lines)


def _normalize_medicines(raw_medicines: Any) -> List[Dict[str, str]]:
    medicines: List[Dict[str, str]] = []
    if not isinstance(raw_medicines, list):
        return medicines
    for med in raw_medicines:
        if isinstance(med, dict):
            medicines.append({
                "medication": med.get("medication", med.get("name", med.get("med", "Unknown Medicine"))),
                "dosage": med.get("dosage", med.get("dose", "As directed")),
                "frequency": med.get("frequency", med.get("freq", "Once daily")),
                "duration": med.get("duration", "As needed"),
                "instructions": med.get("instructions", med.get("sig", "Take as directed")),
            })
        elif isinstance(med, str) and med.strip():
            medicines.append({
                "medication": med.strip(),
                "dosage": "As directed",
                "frequency": "Once daily",
                "duration": "As needed",
                "instructions": "Take as directed",
            })
    return medicines


def _assemble_clinical_state(
    *,
    sub_bulleted: str,
    obj_bulleted: str,
    assess_bulleted: str,
    plan_bulleted: str,
    rx_data: Dict[str, Any],
    admin: Dict[str, Any],
    patient_summary: str,
    cleaned_transcript: str | None = None,
) -> Dict[str, Any]:
    state_update: Dict[str, Any] = {
        "soap": {
            "subjective": sub_bulleted,
            "objective": obj_bulleted,
            "assessment": assess_bulleted,
            "plan": plan_bulleted,
        },
        "rx": {
            "diagnosis": rx_data.get("diagnosis"),
            "medicines": rx_data.get("medicines", []),
            "advice": rx_data.get("advice"),
            "follow_up": rx_data.get("follow_up"),
            "confidence_score": 0.98,
        },
        "billing": {
            "vitals_check": admin.get("vitals_check"),
            "complexity": admin.get("complexity"),
            "codes": admin.get("billing_codes", []),
        },
        "cds": {"risks": admin.get("risk_indicators", [])},
        "patient_summary": patient_summary,
    }
    if cleaned_transcript:
        state_update["cleaned_text"] = cleaned_transcript
    return state_update


async def _run_unified_intelligence(source_text: str, historical_context: str) -> Dict[str, Any]:
    from app.services.intelligence_service import extract_clinical_unified
    import asyncio

    unified = await asyncio.to_thread(extract_clinical_unified, source_text, historical_context)

    sub_bulleted = ensure_bulleted_lines(unified.get("subjective"))
    obj_bulleted = ensure_bulleted_lines(unified.get("objective"))
    assess_bulleted = ensure_bulleted_lines(unified.get("assessment_text"))
    plan_bulleted = ensure_bulleted_lines(unified.get("plan_text"))

    patient_summary = str(unified.get("patient_summary", "")).strip()
    patient_summary = re.sub(r'^["\']|["\']$', '', patient_summary)
    patient_summary = re.sub(
        r'^(Narrative|Synthesis|Clinical Narrative|Summary):\s*',
        '',
        patient_summary,
        flags=re.IGNORECASE,
    )

    rx_data = {
        "diagnosis": unified.get("diagnosis", "Clinical Encounter"),
        "medicines": _normalize_medicines(unified.get("medicines", [])),
        "advice": unified.get("advice", ""),
        "follow_up": unified.get("follow_up", ""),
    }
    admin = {
        "vitals_check": unified.get("vitals_check", False),
        "complexity": unified.get("complexity", "Moderate"),
        "billing_codes": unified.get("billing_codes", []),
        "risk_indicators": unified.get("risk_indicators", []),
    }
    cleaned = unified.get("cleaned_transcript") or source_text

    return _assemble_clinical_state(
        sub_bulleted=sub_bulleted,
        obj_bulleted=obj_bulleted,
        assess_bulleted=assess_bulleted,
        plan_bulleted=plan_bulleted,
        rx_data=rx_data,
        admin=admin,
        patient_summary=patient_summary or "Clinical encounter documented.",
        cleaned_transcript=cleaned.strip() if cleaned else None,
    )


async def _run_parallel_intelligence(source_text: str) -> Dict[str, Any]:
    from app.services.intelligence_service import (
        extract_subjective_objective,
        extract_assessment_plan,
        extract_rx_parallel,
        extract_admin_parallel,
    )
    from app.services.llm_factory import get_utility_llm
    import asyncio

    tasks = [
        asyncio.to_thread(extract_subjective_objective, source_text),
        asyncio.to_thread(extract_assessment_plan, source_text),
        asyncio.to_thread(extract_rx_parallel, source_text),
        asyncio.to_thread(extract_admin_parallel, source_text),
    ]
    so, ap, rx_data, admin = await asyncio.gather(*tasks)

    sub_bulleted = ensure_bulleted_lines(so.get("subjective"))
    obj_bulleted = ensure_bulleted_lines(so.get("objective"))
    assess_bulleted = ensure_bulleted_lines(ap.get("assessment_text"))
    plan_bulleted = ensure_bulleted_lines(ap.get("plan_text"))

    narrative_prompt = f"""You are a senior clinical auditor. Synthesize the following encounter into a single, high-fidelity 1-2 line clinical narrative for the medical record header.
    Focus ONLY on key symptoms, primary diagnosis, and the immediate treatment/clinical pathway.
    STRICTLY 1-2 sentences. DO NOT include section prefixes like "Assessment:" or "Plan:".

    Subjective:
    {sub_bulleted}

    Assessment:
    {assess_bulleted}

    Plan:
    {plan_bulleted}

    Concise 1-2 line synthesis:"""

    narrative_llm = get_utility_llm()
    narrative_res = await narrative_llm.ainvoke(narrative_prompt)
    patient_summary = narrative_res.content.strip()
    patient_summary = re.sub(r'^["\']|["\']$', '', patient_summary)
    patient_summary = re.sub(
        r'^(Narrative|Synthesis|Clinical Narrative|Summary):\s*',
        '',
        patient_summary,
        flags=re.IGNORECASE,
    )

    return _assemble_clinical_state(
        sub_bulleted=sub_bulleted,
        obj_bulleted=obj_bulleted,
        assess_bulleted=assess_bulleted,
        plan_bulleted=plan_bulleted,
        rx_data=rx_data,
        admin=admin,
        patient_summary=patient_summary,
    )


async def intelligence_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clinical intelligence: unified single-pass (default) or legacy 4-way parallel extraction.
    """
    source_text = state.get("cleaned_text") or state.get("transcript", "")
    if not source_text:
        return {}

    historical_context = state.get("historical_context", "")

    try:
        if settings.clinical_unified_extraction:
            logger.info("🧠 Unified clinical extraction (single LLM pass)")
            return await _run_unified_intelligence(source_text, historical_context)
        logger.info("🧠 Parallel micro-extraction (legacy mode)")
        return await _run_parallel_intelligence(source_text)
    except Exception as e:
        logger.error(f"❌ Intelligence node failed: {e}")
        raise
