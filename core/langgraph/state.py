from typing import TypedDict, Optional, List, Dict, Any, Annotated
import operator
from app.schemas.rx_schema import Prescription
from app.schemas.billing_schema import BillingAnalysis
from app.schemas.cds_schema import CDSAnalysis

def take_last(left: Any, right: Any) -> Any:
    return right

class RxState(TypedDict, total=False):
    audio_path: Annotated[str, take_last]
    language: Annotated[Optional[str], take_last]
    transcript: Annotated[str, take_last]
    historical_context: Annotated[str, take_last]
    cleaned_text: Annotated[str, take_last]
    rx: Annotated[Prescription, take_last]
    validation_errors: Annotated[List[str], operator.add]
    rx_text: Annotated[str, take_last]
    billing: Annotated[BillingAnalysis, take_last]
    cds: Annotated[CDSAnalysis, take_last]
    rounds_reviews: Annotated[Dict[str, Any], operator.ior]
    rounds_report: Annotated[Dict[str, Any], take_last]
    referral_data: Annotated[Optional[Dict[str, Any]], take_last]
    wellness_data: Annotated[Optional[Dict[str, Any]], take_last]
    soap: Annotated[Optional[Dict[str, str]], take_last]
    summary_sections: Annotated[Optional[Dict[str, str]], take_last]
    patient_summary: Annotated[Optional[str], take_last]
    to_email: Annotated[Optional[str], take_last]
    email_subject: Annotated[Optional[str], take_last]
    email_status: Annotated[Optional[str], take_last]
    email_message_id: Annotated[Optional[str], take_last]
    email_error: Annotated[Optional[str], take_last]
    verification_audit: Annotated[List[str], operator.add]
