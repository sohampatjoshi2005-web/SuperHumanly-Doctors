from typing import List, Optional
from pydantic import BaseModel, Field

class RiskIndicator(BaseModel):
    """
    Represents a clinical risk identified by the AI during a patient encounter.
    """
    type: str = Field(description="The category of clinical risk (e.g., Sepsis, Fall Risk, Pressure Ulcer, Cardiac Distress)")
    severity: str = Field(description="Severity level: High, Moderate, or Low")
    evidence: str = Field(description="The specific snippet or evidence from the transcript that supports this indicator")
    action_recommendation: str = Field(description="A brief, non-prescriptive suggestion for clinical follow-up")

class CDSAnalysis(BaseModel):
    """
    The collection of clinical risks identified in an encounter.
    """
    risks: List[RiskIndicator] = Field(default_factory=list)
    summary: str = Field(description="A brief overall summary of the clinical risk profile for this encounter")
