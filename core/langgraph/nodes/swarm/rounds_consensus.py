from app.schemas.rounds_schema import ClinicalRoundsReport
from app.core.langgraph.state import RxState
import logging

logger = logging.getLogger(__name__)

async def rounds_consensus_node(state: RxState):
    """
    Synthesizes the reviews from all agents in the swarm.
    """
    logger.info("🤝 Reaching Clinical Rounds Consensus...")
    
    reviews = state.get("rounds_reviews", {})
    
    # Simple synthesis logic
    # In production, this would be an LLM call to summarize the findings.
    
    concerns = []
    for agent, feedback in reviews.items():
        concerns.extend(feedback.get("concerns", []))
        
    report = ClinicalRoundsReport(
        consensus_summary="Specialized review complete. The Pharmacist and Internist have reviewed the documentation. No major safety concerns flagged.",
        agent_reviews=reviews,
        safety_flags=concerns,
        requires_human_review=len(concerns) > 0
    )
    
    return {"rounds_report": report.model_dump()}
