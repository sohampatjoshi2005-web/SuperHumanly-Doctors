from typing import Dict, Any
from app.utils.safety_checks import find_missing_fields


async def validation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    rx = state.get("rx")
    if rx is None:
        return {"validation_errors": ["rx_missing"]}

    missing = find_missing_fields(rx)
    return {"validation_errors": missing}
