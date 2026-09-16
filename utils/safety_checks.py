from typing import List
from app.schemas.rx_schema import Prescription


def find_missing_fields(rx) -> List[str]:
    missing = []
    
    # Handle both dict and Pydantic object
    medicines = rx.get("medicines", []) if isinstance(rx, dict) else getattr(rx, "medicines", [])
    
    for idx, med in enumerate(medicines, start=1):
        # Handle medicine as dict or object
        dosage = med.get("dosage") if isinstance(med, dict) else getattr(med, "dosage", None)
        frequency = med.get("frequency") if isinstance(med, dict) else getattr(med, "frequency", None)
        duration = med.get("duration") if isinstance(med, dict) else getattr(med, "duration", None)
        
        if not dosage:
            missing.append(f"medicine[{idx}].dosage")
        if not frequency:
            missing.append(f"medicine[{idx}].frequency")
        if not duration:
            missing.append(f"medicine[{idx}].duration")
    return missing
