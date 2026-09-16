from langgraph.graph import StateGraph, END

from app.core.config import settings
from app.core.langgraph.nodes.transcription import transcription_node
from app.core.langgraph.nodes.cleanup import cleanup_node
from app.core.langgraph.nodes.validation import validation_node
from app.core.langgraph.nodes.formatting import formatting_node
from app.core.langgraph.nodes.email import email_node
from app.core.langgraph.nodes.swarm.pharmacist_agent import pharmacist_review_node
from app.core.langgraph.nodes.swarm.internist_agent import internist_review_node
from app.core.langgraph.nodes.swarm.rounds_consensus import rounds_consensus_node
from app.core.langgraph.nodes.verification import verification_node
from app.core.langgraph.nodes.intelligence import intelligence_node
from app.core.langgraph.nodes.finalize import finalize_node
from app.core.langgraph.state import RxState


def build_graph():
    """
    Clinical pipeline graph with configurable swarm, cleanup, and verification modes.
    Always ends with a single finalize → email path (no duplicate email runs).
    """
    graph = StateGraph(RxState)

    graph.add_node("transcription", transcription_node)
    graph.add_node("cleanup", cleanup_node)
    graph.add_node("intelligence", intelligence_node)
    graph.add_node("validation", validation_node)
    graph.add_node("formatting", formatting_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("email", email_node)
    graph.add_node("verification", verification_node)

    graph.set_entry_point("transcription")
    graph.add_edge("transcription", "intelligence")

    if settings.clinical_enable_cleanup_node:
        graph.add_edge("transcription", "cleanup")

    graph.add_edge("intelligence", "validation")
    graph.add_edge("validation", "formatting")
    graph.add_edge("formatting", "finalize")

    if not settings.clinical_async_verification:
        graph.add_edge("intelligence", "verification")
        graph.add_edge("verification", "finalize")

    if settings.clinical_enable_swarm:
        graph.add_node("pharmacist_review", pharmacist_review_node)
        graph.add_node("internist_review", internist_review_node)
        graph.add_node("consensus", rounds_consensus_node)
        graph.add_edge("intelligence", "pharmacist_review")
        if settings.clinical_enable_cleanup_node:
            graph.add_edge("intelligence", "internist_review")
            graph.add_edge("cleanup", "internist_review")
        else:
            graph.add_edge("intelligence", "internist_review")
        graph.add_edge("pharmacist_review", "consensus")
        graph.add_edge("internist_review", "consensus")
        graph.add_edge("consensus", "finalize")

    graph.add_edge("finalize", "email")
    graph.add_edge("email", END)

    return graph.compile()
