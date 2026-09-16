from app.services.llm_factory import get_chat_llm
from app.core.langgraph.state import RxState
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

async def wellness_node(state: RxState):
    """
    Detects patient follow-up needs and adherence requirements.
    """
    logger.info("🧘 Analyzing patient wellness & follow-up needs...")
    
    transcript = state.get("cleaned_text")
    
    # AI detection logic (simulated)
    # In production, Gemini would extract the specific due dates
    wellness_data = {
        "followups": [
            {
                "instruction": "Blood pressure check and medication review.",
                "due_date": (datetime.utcnow() + timedelta(days=14)).isoformat(),
                "priority": "Moderate"
            }
        ],
        "adherence_plan": {
            "monitored_meds": ["Metformin"],
            "frequency": "Daily"
        }
    }
    
    return {"wellness_data": wellness_data}
