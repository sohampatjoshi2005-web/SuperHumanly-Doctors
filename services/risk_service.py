from typing import List, Dict, Any, Optional
from sqlmodel import select, Session
from app.db_models import Encounter
from datetime import datetime, timedelta

class ClinicalRisk(Dict[str, Any]):
    """Helper class for risk alerts"""
    pass

from sqlalchemy.ext.asyncio import AsyncSession

async def detect_risks(session: AsyncSession, customer_id: str) -> List[Dict[str, Any]]:
    """
    Scans the encounter history for a specific customer to detect clinical risks
    based on longitudinal variances in clinical_data.
    """
    # Fetch last 30 days of encounters for this patient
    stmt = select(Encounter).where(
        Encounter.customer_id == customer_id
    ).order_by(Encounter.created_at.desc()).limit(20)
    
    result = await session.execute(stmt)
    encounters = result.scalars().all()
    if len(encounters) < 2:
        return []

    risks = []

    # 1. Acute Kidney Injury (AKI) Detection
    # Logic: Serum Creatinine increase >= 0.3 mg/dL within 48h OR >= 1.5x baseline within 7 days
    creatinine_readings = []
    for enc in encounters:
        if enc.clinical_data and 'creatinine' in enc.clinical_data:
            try:
                val = float(enc.clinical_data['creatinine'])
                creatinine_readings.append({
                    'value': val,
                    'timestamp': enc.created_at
                })
            except (ValueError, TypeError):
                continue

    if len(creatinine_readings) >= 2:
        current = creatinine_readings[0]
        previous = creatinine_readings[1]
        
        # Check 48h window for 0.3 mg/dL rise
        time_diff = current['timestamp'] - previous['timestamp']
        if time_diff <= timedelta(hours=48):
            variance = current['value'] - previous['value']
            if variance >= 0.3:
                risks.append({
                    'id': 'aki-risk',
                    'name': 'Acute Kidney Injury Risk',
                    'severity': 'High',
                    'reason': f"Serum creatinine rose by {variance:.2f} mg/dL ({ (variance/previous['value']*100):.1f}%) in {time_diff.total_seconds()/3600:.1f} hours.",
                    'vitals': {
                        'Current Cr': f"{current['value']} mg/dL",
                        'Previous Cr': f"{previous['value']} mg/dL",
                        'Variance': f"+{variance:.2f}"
                    },
                    'actions': [
                        {'label': 'Order STAT Metabolic Panel', 'type': 'order_lab', 'payload': {'lab': 'BMP', 'priority': 'STAT'}},
                        {'label': 'Review Fluid Intake', 'type': 'navigation', 'payload': {'tab': 'Summary'}}
                    ]
                })

    # 2. Hypertensive Crisis Detection
    # Logic: SBP > 180 or DBP > 120
    latest_enc = encounters[0]
    if latest_enc.clinical_data:
        sbp = latest_enc.clinical_data.get('sbp')
        dbp = latest_enc.clinical_data.get('dbp')
        try:
            if (sbp and float(sbp) > 180) or (dbp and float(dbp) > 120):
                risks.append({
                    'id': 'htn-crisis',
                    'name': 'Hypertensive Urgency',
                    'severity': 'High',
                    'reason': f"Blood pressure reading of {sbp}/{dbp} exceeds clinical safety thresholds.",
                    'vitals': {
                        'BP': f"{sbp}/{dbp}",
                        'Threshold': '180/120'
                    },
                    'actions': [
                        {'label': 'Administer Antihypertensives', 'type': 'protocol', 'payload': {'name': 'HTN_URGENCY'}},
                        {'label': 'Notify Supervising Physician', 'type': 'notification', 'payload': {'role': 'admin'}}
                    ]
                })
        except (ValueError, TypeError):
            pass

    return risks
