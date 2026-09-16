from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.rx_schema import Medicine
from app.schemas.billing_schema import BillingCode
from app.schemas.cds_schema import RiskIndicator

class UnifiedEncounterAnalysis(BaseModel):
    # Clinical Summary (Structured)
    clinical_notes: str = Field(description="Comprehensive clinical narrative including history, exam findings, assessment, and plan.")
    
    # Prescription Data
    diagnosis: Optional[str] = Field(description="Primary clinical diagnosis.")
    medicines: List[Medicine] = Field(default_factory=list, description="List of prescribed medicines.")
    advice: Optional[str] = Field(description="General patient advice and instructions.")
    follow_up: Optional[str] = Field(description="Follow-up timeline and criteria.")
    
    # Billing & Complexity
    vitals_check: bool = Field(description="Whether vitals were captured or mentioned.")
    complexity: str = Field(description="Clinical complexity: High, Moderate, or Low.")
    codes_reasoning: str = Field(description="Logic behind the selected codes.")
    billing_codes: List[BillingCode] = Field(default_factory=list, description="Suggested billing codes (ICD-10, CPT).")
    
    # Clinical Data (Structured Sections for UI)
    summary_sections: Dict[str, str] = Field(
        default_factory=dict,
        description="Structured sections: {'Symptoms': '...', 'Assessment': '...', 'Plan': '...', 'Red Flags': '...', 'Follow-up': '...'}"
    )

    # SOAP Note (Industry Standard)
    subjective: Optional[str] = Field(None, description="Patient's reported symptoms and history (Subjective).")
    objective: Optional[str] = Field(None, description="Clinical findings, vitals, and physical exam data (Objective).")
    assessment_text: Optional[str] = Field(None, description="Clinical assessment and diagnosis (Assessment).")
    plan_text: Optional[str] = Field(None, description="Comprehensive treatment plan (Plan).")
    
    # Clinical Data (Legacy/Overview)

    vitals_and_labs: Optional[Dict[str, Any]] = Field(default=None, description="Structured clinical signals extracted from the encounter (vitals, labs).")
    risk_indicators: List[RiskIndicator] = Field(default_factory=list, description="Extracted clinical risk flags (Sepsis, Fall Risk, etc.)")
    patient_summary: str = Field(description="A jargon-free, patient-friendly summary of the encounter")
    
    # Metadata
    confidence_score: float = Field(default=1.0, description="Overall confidence in the analysis.")

