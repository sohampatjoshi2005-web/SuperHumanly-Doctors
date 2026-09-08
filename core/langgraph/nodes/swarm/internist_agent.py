from app.services.llm_factory import get_chat_llm
from app.schemas.rounds_schema import AgentFeedback
from app.core.langgraph.state import RxState
import logging

logger = logging.getLogger(__name__)

async def internist_review_node(state: RxState):
    """
    Simulates a specialized Internist agent reviewing the clinical narrative vs. diagnosis.
    """
    logger.info("🩺 Internist Agent entering the room...")
    
    transcript = state.get("cleaned_text")
    rx = state.get("rx")
    
    # Simulate internal reasoning
    feedback = AgentFeedback(
        agent_name="Internist",
        assessment="Clinical presentation aligns well with the proposed treatment plan. Patient reports classic symptoms of stable Type 2 Diabetes.",
        concerns=[],
        recommendations=["Monitor A1c in 3 months."],
        confidence=0.98
    )
    
    return {"rounds_reviews": {"internist": feedback.model_dump()}}
