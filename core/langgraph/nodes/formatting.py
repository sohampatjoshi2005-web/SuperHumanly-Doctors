from typing import Dict, Any
from app.services.formatting_service import format_prescription_text


async def formatting_node(state: Dict[str, Any]) -> Dict[str, Any]:
    rx = state.get("rx")
    if rx is None:
        raise ValueError("rx is required")

    rx_text = format_prescription_text(rx)
    return {"rx_text": rx_text}
