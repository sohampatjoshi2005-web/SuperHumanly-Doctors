from contextvars import ContextVar
from typing import Optional

# Context variable for the current clinic ID
_clinic_id_ctx: ContextVar[Optional[str]] = ContextVar("clinic_id", default=None)

def set_clinic_id(clinic_id: str) -> None:
    """Set the current clinic ID in the request context."""
    _clinic_id_ctx.set(clinic_id)

def get_clinic_id() -> Optional[str]:
    """Retrieve the current clinic ID from the request context."""
    return _clinic_id_ctx.get()

def clear_clinic_id() -> None:
    """Clear the current clinic ID context."""
    _clinic_id_ctx.set(None)
