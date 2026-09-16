from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class AgentFeedback(BaseModel):
    agent_name: str
    assessment: str
    concerns: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0)

class ClinicalRoundsReport(BaseModel):
    consensus_summary: str
    agent_reviews: Dict[str, AgentFeedback]
    safety_flags: List[str] = Field(default_factory=list)
    requires_human_review: bool = Field(default=False)
