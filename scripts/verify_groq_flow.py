import os
import sys
import asyncio
from datetime import datetime

# Add current directory to path
sys.path.append(os.getcwd())

from app.services.intelligence_service import analyze_encounter_unified

SAMPLE_TRANSCRIPT = """
Doctor: Good morning, Mr. Miller. How are you feeling today?
Patient: Not great, doc. I've had this persistent cough for about two weeks now, and it's getting worse at night. I also feel a bit feverish.
Doctor: I see. Let's take your vitals. Temperature is 101.2 F, Heart rate is 88. Lungs sound a bit congested on the lower right side.
Patient: Is it serious?
Doctor: It looks like community-acquired pneumonia. I'm going to prescribe Amoxicillin 500mg, three times a day for 7 days. Also, take some rest and drink plenty of fluids. I want to see you back in a week.
Patient: Okay, thank you doc.
"""

async def verify_clinical_intelligence():
    print("🚀 Verifying Clinical Intelligence Flow (Groq -> Gemini Fallback)...")
    
    # Ensure env is loaded
    from app.core.config import settings
    print(f"Current Provider: {settings.llm_provider}")
    print(f"Groq Key Present: {'Yes' if settings.groq_api_key else 'No'}")
    print(f"Gemini Key Present: {'Yes' if settings.gemini_api_key else 'No'}")

    try:
        start_time = datetime.now()
        print("🧠 Analyzing transcript...")
        analysis = analyze_encounter_unified(SAMPLE_TRANSCRIPT)
        duration = (datetime.now() - start_time).total_seconds()
        
        print(f"✅ Analysis Complete in {duration:.2f}s")
        print(f"Diagnosis: {analysis.diagnosis}")
        print(f"Complexity: {analysis.complexity}")
        print(f"Vitals Checked: {analysis.vitals_check}")
        print(f"Billing Codes: {[c.code for c in analysis.billing_codes]}")
        
        # Check if output is structured correctly
        assert analysis.diagnosis is not None
        assert len(analysis.billing_codes) > 0
        
        print("\n✨ CLINICAL INTELLIGENCE VERIFIED")
        
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_clinical_intelligence())
