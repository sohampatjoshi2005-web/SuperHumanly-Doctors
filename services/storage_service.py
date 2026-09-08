from typing import List, Optional

from sqlmodel import select

from app.db import get_session, init_db
from app.db_models import Customer, Encounter, Referral, PatientFollowup


def ensure_db() -> None:
    init_db()


def create_customer(name: str) -> Customer:
    ensure_db()
    customer = Customer(name=name.strip())
    with get_session() as session:
        session.add(customer)
        session.commit()
        session.refresh(customer)
    return customer


def list_customers() -> List[Customer]:
    ensure_db()
    with get_session() as session:
        return list(session.exec(select(Customer).order_by(Customer.created_at.desc())))


def get_customer(customer_id: str) -> Optional[Customer]:
    ensure_db()
    with get_session() as session:
        return session.get(Customer, customer_id)


def create_encounter(encounter: Encounter) -> Encounter:
    ensure_db()
    with get_session() as session:
        session.add(encounter)
        session.commit()
        session.refresh(encounter)
        return encounter


def list_encounters(customer_id: str) -> List[Encounter]:
    ensure_db()
    with get_session() as session:
        stmt = select(Encounter).where(Encounter.customer_id == customer_id).order_by(Encounter.created_at.desc())
        return list(session.exec(stmt))


def get_encounter(encounter_id: str) -> Optional[Encounter]:
    ensure_db()
    with get_session() as session:
        return session.get(Encounter, encounter_id)


def patch_encounter_clinical(
    encounter_id: str,
    *,
    soap: Optional[dict] = None,
    billing: Optional[dict] = None,
    audit_logs: Optional[list] = None,
) -> None:
    """Apply post-hoc QA corrections from the verification node."""
    ensure_db()
    with get_session() as session:
        enc = session.get(Encounter, encounter_id)
        if not enc:
            return
        clinical_data = dict(enc.clinical_data or {})
        if soap:
            clinical_data["soap"] = soap
        if audit_logs:
            clinical_data["verification_audit"] = audit_logs
        enc.clinical_data = clinical_data
        if billing:
            codes = billing.get("codes", [])
            if codes:
                enc.codes_json = {"codes": codes}
            if billing.get("complexity"):
                enc.complexity = billing.get("complexity")
            if "vitals_check" in billing:
                enc.vitals_check = billing.get("vitals_check")
        session.add(enc)
        session.commit()


def update_encounter_email(
    encounter_id: str,
    *,
    to_email: Optional[str],
    subject: Optional[str],
    status: Optional[str],
    message_id: Optional[str],
) -> None:
    ensure_db()
    with get_session() as session:
        enc = session.get(Encounter, encounter_id)
        if not enc:
            return
        enc.email_to = to_email
        enc.email_subject = subject
        enc.email_status = status
        enc.email_message_id = message_id
        session.add(enc)
        session.commit()


def create_referral(referral: Referral) -> Referral:
    ensure_db()
    with get_session() as session:
        session.add(referral)
        session.commit()
        session.refresh(referral)
        return referral


def create_followups(followups: List[PatientFollowup]) -> List[PatientFollowup]:
    ensure_db()
    with get_session() as session:
        for f in followups:
            session.add(f)
        session.commit()
        for f in followups:
            session.refresh(f)
        return followups
