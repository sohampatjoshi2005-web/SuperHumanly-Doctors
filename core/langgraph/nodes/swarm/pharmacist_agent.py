from app.services.llm_factory import get_chat_llm
from app.schemas.rounds_schema import AgentFeedback
from app.core.langgraph.state import RxState
import logging

logger = logging.getLogger(__name__)

async def pharmacist_review_node(state: RxState):
    """
    Simulates a specialized Pharmacist agent reviewing the prescription.
    """
    logger.info("💊 Pharmacist Agent entering the room...")
    
    rx = state.get("rx")
    if not rx:
        return {"rounds_reviews": {}}

    # ... (LLM logic)
    
    # Simulate LLM call or real one if keys exist
    # For now, we simulate structured output
    feedback = AgentFeedback(
        agent_name="Pharmacist",
        assessment="Prescription reviewed. No major contraindications detected with the current patient history.",
        concerns=[],
        recommendations=["Ensure patient is advised to take Metformin with meals to reduce GI side effects."],
        confidence=0.95
    )
    
    return {"rounds_reviews": {"pharmacist": feedback.model_dump()}}
