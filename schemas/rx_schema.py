from typing import List, Optional, Any
from pydantic import BaseModel, Field
from pydantic import field_validator


class Medicine(BaseModel):
    name: str = Field(description="Name of the medicine (e.g., Paracetamol, Amoxicillin)")
    dosage: str = Field(default="", description="Amount per dose (e.g., 500 mg, 1 tablet, 5 ml)")
    frequency: str = Field(default="", description="How often to take (e.g., twice daily, every 8 hours)")
    duration: str = Field(default="", description="Total duration (e.g., 5 days, 2 weeks)")
    route: Optional[str] = Field(default=None, description="Route (e.g., oral, IV, topical)")
    instructions: Optional[str] = Field(default=None, description="Special instructions (e.g., after food)")


class Prescription(BaseModel):
    patient_name: Optional[str] = Field(default=None, description="Patient name")
    age: Optional[int] = Field(default=None, description="Age in years")
    gender: Optional[str] = Field(default=None, description="Gender")
    diagnosis: Optional[str] = Field(default=None, description="Diagnosis or condition")
    medicines: List[Medicine] = Field(description="List of prescribed medicines")
    advice: Optional[str] = Field(default=None, description="General advice")
    follow_up: Optional[str] = Field(default=None, description="Follow-up instructions")
    confidence_score: float = Field(default=0.98, description="LLM self-assessed extraction confidence score (0.0 to 1.0)")

    @field_validator("diagnosis", "advice", "follow_up", mode="before")
    @classmethod
    def _coerce_list_to_string(cls, value: Any):
        # Ollama models sometimes emit lists for these fields; accept and join.
        if value is None:
            return None
        if isinstance(value, list):
            parts = [str(v).strip() for v in value if str(v).strip()]
            return ", ".join(parts) if parts else None
        return value
