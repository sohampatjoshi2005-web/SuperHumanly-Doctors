from app.schemas.rx_schema import Prescription


def format_prescription_text(rx) -> str:
    lines = []
    
    # Helper to get values from dict or object
    def g(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    lines.append("CLINICAL DOCUMENTATION & PRESCRIPTION")
    lines.append("=" * 40)
    
    patient_name = g(rx, "patient_name")
    if patient_name:
        lines.append(f"PATIENT: {patient_name}")
        
    age = g(rx, "age")
    if age is not None:
        lines.append(f"AGE: {age}")
        
    gender = g(rx, "gender")
    if gender:
        lines.append(f"GENDER: {gender}")
    
    lines.append("-" * 40)
    
    diagnosis = g(rx, "diagnosis")
    if diagnosis:
        confidence = g(rx, "confidence_score", 1.0)
        lines.append(f"PRIMARY DIAGNOSIS: {diagnosis}")
        lines.append(f"CONFIDENCE: {confidence * 100:.1f}%")
    
    lines.append("\nPHARMACOLOGICAL INTERVENTIONS:")
    medicines = g(rx, "medicines", [])
    if not medicines:
        lines.append("No pharmacological treatment prescribed at this time.")
    else:
        for idx, med in enumerate(medicines, start=1):
            med_name = g(med, "name") or g(med, "medication") or "Unknown Medicine"
            dosage = g(med, "dosage", "N/A")
            frequency = g(med, "frequency", "N/A")
            duration = g(med, "duration", "N/A")
            instructions = g(med, "instructions") or g(med, "sig")
            
            lines.append(f"{idx}. {med_name.upper()}")
            lines.append(f"   Dose/Freq: {dosage} {frequency}")
            lines.append(f"   Duration: {duration}")
            if instructions:
                lines.append(f"   Patient Instructions: {instructions}")
            lines.append("")

    lines.append("NON-PHARMACOLOGICAL ADVICE & CLINICAL GUIDANCE:")
    advice = g(rx, "advice")
    if advice:
        lines.append(f"- {advice}")
    else:
        lines.append("- Continue supportive care as discussed.")

    lines.append("\nFOLLOW-UP PLAN:")
    follow_up = g(rx, "follow_up")
    if follow_up:
        lines.append(f"- {follow_up}")
    else:
        lines.append("- Return as needed if symptoms fail to resolve or exacerbate.")

    lines.append("\n" + "=" * 40)
    lines.append("DISCLAIMER: This documentation is generated with AI assistance. Clinical verification is mandatory before implementation.")
    
    return "\n".join(lines).strip()
