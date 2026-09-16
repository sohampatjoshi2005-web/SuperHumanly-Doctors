from typing import Dict, Any
from app.services.rx_service import extract_prescription


async def extraction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    # Use cleaned_text if available, otherwise fallback to raw transcript for speculative speed
    source_text = state.get("cleaned_text") or state.get("transcript", "")
    rx = await extract_prescription(source_text)
    # Ensure serialization by converting Pydantic model to dict
    return {"rx": rx.model_dump() if hasattr(rx, "model_dump") else rx}
