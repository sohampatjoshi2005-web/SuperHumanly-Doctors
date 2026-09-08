from typing import List, Dict, Any
from sqlmodel import select, func, and_
from app.db import get_session
from app.db_models import Encounter, Customer, User, Clinic
from datetime import datetime, timedelta

class InstitutionalService:
    @staticmethod
    def get_clinic_stats(clinic_id: str) -> Dict[str, Any]:
        """
        Aggregate clinic-wide stats across all providers.
        """
        with get_session() as session:
            # 1. Total Base Counts
            pat_count = session.exec(select(func.count(Customer.id)).where(Customer.clinic_id == clinic_id)).one()
            enc_count = session.exec(select(func.count(Encounter.id)).where(Encounter.clinic_id == clinic_id)).one()
            doc_count = session.exec(select(func.count(User.id)).where(User.clinic_id == clinic_id, User.role == "doctor")).one()
            
            # 2. Risk Hotspots
            # Simple aggregation of complexity as a proxy for risk hotspots
            high_risk = session.exec(select(func.count(Encounter.id)).where(Encounter.clinic_id == clinic_id, Encounter.complexity == "High")).one()
            
            # 3. Documentation Velocity (Average duration per encounter in minutes)
            # This requires a 'duration' field or calculation. For now, we'll estimate based on complexity.
            avg_velocity = 88.5 # Placeholder for clinic efficiency
            
            # 4. Specialty Distribution
            # (Assuming encounters or customers have a specialty field, or mapping from doctor specialty)
            
            return {
                "total_patients": pat_count,
                "total_encounters": enc_count,
                "total_doctors": doc_count,
                "high_risk_encounters": high_risk,
                "efficiency_score": avg_velocity,
                "institutional_readiness": min(100, 40 + (enc_count * 0.5))
            }

    @staticmethod
    def get_provider_benchmarks(clinic_id: str) -> List[Dict[str, Any]]:
        """
        Compare provider performance within a clinic.
        """
        with get_session() as session:
            # Get all doctors in clinic
            doctors = session.exec(select(User).where(User.clinic_id == clinic_id, User.role == "doctor")).all()
            
            benchmarks = []
            for doc in doctors:
                enc_count = session.exec(select(func.count(Encounter.id)).where(Encounter.doctor_id == str(doc.id))).one()
                high_comp = session.exec(select(func.count(Encounter.id)).where(Encounter.doctor_id == str(doc.id), Encounter.complexity == "High")).one()
                
                benchmarks.append({
                    "doctor_name": doc.full_name or doc.username,
                    "encounter_volume": enc_count,
                    "complexity_ratio": f"{high_comp/max(1, enc_count)*100:.1f}%",
                    "efficiency_index": 70 + (enc_count * 2) # Mock index
                })
            
            return benchmarks

    @staticmethod
    def get_efficiency_benchmarks(clinic_id: str) -> List[Dict[str, Any]]:
        """
        Detailed time-to-sign analysis.
        """
        with get_session() as session:
            doctors = session.exec(select(User).where(User.clinic_id == clinic_id, User.role == "doctor")).all()
            
            reports = []
            for doc in doctors:
                # Calculate average duration for this doctor
                stmt = select(func.avg(Encounter.documentation_duration_sec)).where(
                    Encounter.doctor_id == str(doc.id),
                    Encounter.documentation_duration_sec != None
                )
                avg_duration = session.exec(stmt).one() or 0
                
                reports.append({
                    "doctor_name": doc.full_name or doc.username,
                    "avg_duration_sec": int(avg_duration),
                    "status": "Optimal" if avg_duration < 45 else "Monitor" if avg_duration < 90 else "Review Needed"
                })
            return reports

    @staticmethod
    def get_diagnostic_accuracy_report(clinic_id: str) -> List[Dict[str, Any]]:
        """
        Rankings based on documentation precision and code alignment.
        """
        with get_session() as session:
            doctors = session.exec(select(User).where(User.clinic_id == clinic_id, User.role == "doctor")).all()
            
            accuracy_data = []
            for doc in doctors:
                encounters = session.exec(select(Encounter).where(
                    Encounter.doctor_id == str(doc.id),
                    Encounter.original_codes_json != None
                )).all()
                
                total_alignment = 0
                for enc in encounters:
                    orig = set(c.get("code") for c in enc.original_codes_json.get("codes", []))
                    final = set(c.get("code") for c in enc.codes_json.get("codes", []))
                    
                    if final:
                        intersection = orig.intersection(final)
                        total_alignment += len(intersection) / len(final)
                    elif not orig:
                        total_alignment += 1 # Both empty is aligned
                
                avg_accuracy = (total_alignment / len(encounters) * 100) if encounters else 100
                
                accuracy_data.append({
                    "doctor_name": doc.full_name or doc.username,
                    "accuracy_score": f"{avg_accuracy:.1f}%",
                    "sample_size": len(encounters)
                })
            return accuracy_data
