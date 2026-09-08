from app.services.billing_service import extract_billing_info


async def billing_node(state):
    """
    LangGraph node to extract billing and coding information from the cleaned transcript.
    """
    transcript = state.get("cleaned_text") or state.get("transcript")
    
    if not transcript:
        return {"billing": None}
        
    billing = await extract_billing_info(transcript)
    # Ensure serialization by converting Pydantic model to dict
    return {"billing": billing.model_dump() if hasattr(billing, "model_dump") else billing}
