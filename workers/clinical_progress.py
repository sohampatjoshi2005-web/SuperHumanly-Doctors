"""Helpers for Celery PROGRESS meta and LangGraph partial results."""
from __future__ import annotations

from typing import Any, Dict, Optional


def build_partial_result(final_state: Dict[str, Any]) -> Dict[str, Any]:
    rx_data = final_state.get("rx") or {}
    billing_data = final_state.get("billing") or {}
    soap = final_state.get("soap") or {}

    diagnosis = None
    medicines = []
    if isinstance(rx_data, dict):
        diagnosis = rx_data.get("diagnosis")
        medicines = rx_data.get("medicines", [])
    else:
        diagnosis = getattr(rx_data, "diagnosis", None)
        medicines = getattr(rx_data, "medicines", []) or []

    billing_codes = []
    if isinstance(billing_data, dict):
        billing_codes = billing_data.get("codes", [])
    else:
        billing_codes = getattr(billing_data, "codes", []) or []

    return {
        "transcript": final_state.get("transcript"),
        "cleaned_text": final_state.get("cleaned_text"),
        "patient_summary": final_state.get("patient_summary"),
        "rx_text": final_state.get("rx_text"),
        "diagnosis": diagnosis,
        "medicines": medicines,
        "billing_codes": billing_codes,
        "soap": soap,
    }
