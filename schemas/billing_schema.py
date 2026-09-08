from typing import List, Optional
from pydantic import BaseModel, Field


class BillingCode(BaseModel):
    code: str = Field(description="ICD-10 or CPT code")
    system: str = Field(description="Coding system (ICD-10-CM or CPT)")
    description: str = Field(description="Detailed description of the code")
    justification: str = Field(description="Clinical justification for this code based on the encounter")
    category: str = Field(description="Category (e.g., Primary Diagnosis, Evaluation & Management)")
    confidence: float = Field(ge=0.0, le=1.0, description="AI confidence score")
    evidence: List[str] = Field(default_factory=list, description="Snippets from transcript as evidence")


class BillingAnalysis(BaseModel):
    vitals_check: bool = Field(description="Whether vitals were discussed or checked")
    complexity: str = Field(description="Clinical complexity level: High, Moderate, or Low")
    codes_reasoning: str = Field(description="Brief overview of the coding logic")
    codes: List[BillingCode] = Field(description="List of suggested ICD-10 and CPT codes")
