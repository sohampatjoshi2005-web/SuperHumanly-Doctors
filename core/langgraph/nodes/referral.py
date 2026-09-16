from app.services.llm_factory import get_chat_llm
from app.core.langgraph.state import RxState
import logging

logger = logging.getLogger(__name__)

async def referral_node(state: RxState):
    """
    Detects if a referral is needed and generates a draft letter.
    """
    logger.info("📄 Checking for clinical referrals...")
    
    transcript = state.get("cleaned_text")
    if "referral" not in transcript.lower() and "consult" not in transcript.lower():
        return {"referral_data": None}

    # ... (LLM logic would go here)
    
    # Simulate structured extraction
    referral_data = {
        "specialty": "Cardiology",
        "reason": "Evaluation of new heart murmur and persistent palpitations.",
        "priority": "Urgent",
        "letter_text": f"Dear Colleague,\n\nI am referring this patient for a Cardiology consultation regarding {state.get('cleaned_text')[:50]}...\n\nSincerely,\nSuperhumanly AI",
        "insurance_notes": "Patient has history of HTN, necessitating urgent cardiac evaluation."
    }
    
    return {"referral_data": referral_data}
