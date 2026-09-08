"""
Intelligence Tools — Real database-backed tools for the LangGraph clinical agent.

These are invoked by the agent graph in intelligence.py when the LLM
decides it needs to fetch data from the database.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional, List
import json as _json

from langchain_core.tools import tool
from sqlmodel import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import async_session_maker
from app.db_models import Customer, Encounter


def _is_postgresql() -> bool:
    url = settings.database_url.lower()
    return "postgresql" in url or url.startswith("postgres://")


def _medicine_names(rx_json: object) -> list[str]:
    if not rx_json or not isinstance(rx_json, dict):
        return []
    medicines = rx_json.get("medicines") or []
    names: list[str] = []
    for med in medicines:
        if isinstance(med, dict):
            name = str(med.get("name", "")).strip()
            if name:
                names.append(name)
    return names


# ---------------------------------------------------------------------------
# Helper: get async session
# ---------------------------------------------------------------------------

async def _get_session() -> AsyncSession:
    if async_session_maker is None:
        raise RuntimeError("Async database not configured")
    return async_session_maker()


# ---------------------------------------------------------------------------
# Tool 1 — Search Patients
# ---------------------------------------------------------------------------

@tool
async def search_patients(query: str) -> str:
    """Search patients by name (case-insensitive). Returns id, name, and registration date."""
    async with await _get_session() as session:
        stmt = (
            select(Customer)
            .where(Customer.name.ilike(f"%{query}%"))
            .limit(20)
        )
        result = await session.execute(stmt)
        patients = result.scalars().all()

        if not patients:
            return f"No patients found matching '{query}'."

        lines = []
        for p in patients:
            lines.append(
                f"- ID: {p.id} | Name: {p.name} | Registered: {p.created_at.strftime('%Y-%m-%d')}"
            )
        return f"Found {len(patients)} patient(s):\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2 — Patient Encounter History
# ---------------------------------------------------------------------------

@tool
async def get_patient_history(patient_id: str) -> str:
    """Fetch the full encounter history for a specific patient (up to 50 encounters). Include diagnosis and medications."""
    async with await _get_session() as session:
        customer = await session.get(Customer, patient_id)
        if not customer:
            return f"Patient with ID '{patient_id}' not found."

        stmt = (
            select(Encounter)
            .where(Encounter.customer_id == patient_id)
            .order_by(Encounter.created_at.desc())
            .limit(50)
        )
        result = await session.execute(stmt)
        encounters = result.scalars().all()

        if not encounters:
            return f"No encounters found for patient '{customer.name}'."

        lines = [f"Patient: {customer.name} (ID: {customer.id})"]
        for enc in encounters:
            diag = enc.diagnosis or "Unspecified"
            rx_list = []
            if enc.rx_json and isinstance(enc.rx_json, dict) and "medicines" in enc.rx_json:
                rx_list = [m.get("name", "") for m in enc.rx_json["medicines"]]
            rx_str = ", ".join(filter(None, rx_list)) or "None"
            complexity = enc.complexity or "N/A"
            lines.append(
                f"- Date: {enc.created_at.strftime('%Y-%m-%d')} | Diagnosis: {diag} | Meds: {rx_str} | Complexity: {complexity}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3 — Recent Encounters
# ---------------------------------------------------------------------------

@tool
async def get_recent_encounters(limit: int = 20) -> str:
    """Fetch the most recent clinical encounters across the practice with patient names, diagnosis, and medications."""
    limit = min(limit, 50)
    async with await _get_session() as session:
        stmt = (
            select(Encounter)
            .order_by(Encounter.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        encounters = result.scalars().all()

        if not encounters:
            return "No encounters found in the system."

        # Resolve patient names
        customer_ids = list({e.customer_id for e in encounters})
        cust_stmt = select(Customer).where(Customer.id.in_(customer_ids))
        cust_result = await session.execute(cust_stmt)
        customers = cust_result.scalars().all()
        cust_map = {c.id: c.name for c in customers}

        lines = [f"Showing {len(encounters)} most recent encounters:"]
        for enc in encounters:
            name = cust_map.get(enc.customer_id, "Unknown")
            diag = enc.diagnosis or "Unspecified"
            rx_list = []
            if enc.rx_json and isinstance(enc.rx_json, dict) and "medicines" in enc.rx_json:
                rx_list = [m.get("name", "") for m in enc.rx_json["medicines"]]
            rx_str = ", ".join(filter(None, rx_list)) or "None"
            lines.append(
                f"- {enc.created_at.strftime('%Y-%m-%d')} | {name} | Diagnosis: {diag} | Meds: {rx_str}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3.5 — Search Clinical Records (Meds/Diag) — SQL Optimized
# ---------------------------------------------------------------------------

@tool
async def search_clinical_records(query: str, search_type: str = "medication") -> str:
    """
    Search for patients based on a medication name or a diagnosis.
    search_type must be 'medication' or 'diagnosis'.
    Returns a list of matching patients and their last encounter dates.
    """
    query = query.strip().lower()
    async with await _get_session() as session:
        if search_type == "medication":
            if _is_postgresql():
                sql = text("""
                    SELECT DISTINCT e.* FROM encounter e, jsonb_array_elements(e.rx_json->'medicines') AS m
                    WHERE m->>'name' ILIKE :query
                    ORDER BY e.created_at DESC LIMIT 20
                """)
                result = await session.execute(sql, {"query": f"%{query}%"})
                encounters = result.all()
            else:
                stmt = (
                    select(Encounter)
                    .order_by(Encounter.created_at.desc())
                    .limit(500)
                )
                result = await session.execute(stmt)
                all_encounters = result.scalars().all()
                encounters = [
                    enc
                    for enc in all_encounters
                    if any(query in name.lower() for name in _medicine_names(enc.rx_json))
                ][:20]
        else:
            if _is_postgresql():
                sql = text("""
                    SELECT * FROM encounter
                    WHERE diagnosis ILIKE :query
                    ORDER BY created_at DESC LIMIT 20
                """)
                result = await session.execute(sql, {"query": f"%{query}%"})
                encounters = result.all()
            else:
                stmt = (
                    select(Encounter)
                    .where(func.lower(Encounter.diagnosis).like(f"%{query}%"))
                    .order_by(Encounter.created_at.desc())
                    .limit(20)
                )
                result = await session.execute(stmt)
                encounters = result.scalars().all()

        if not encounters:
            return f"No records found matching {search_type}: '{query}'."

        customer_ids = list({e.customer_id for e in encounters})
        cust_stmt = select(Customer).where(Customer.id.in_(customer_ids))
        cust_result = await session.execute(cust_stmt)
        customers = cust_result.scalars().all()
        cust_map = {c.id: c.name for c in customers}

        lines = [f"Found {len(encounters)} matching clinical record(s):"]
        for enc in encounters:
            name = cust_map.get(enc.customer_id, "Unknown")
            date_str = enc.created_at.strftime('%Y-%m-%d')
            lines.append(f"- Patient: {name} | Date: {date_str} | Match: {query}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4 — Aggregate Clinical Data — SQL Optimized
# ---------------------------------------------------------------------------

@tool
async def aggregate_clinical_data(metric: str) -> str:
    """Aggregate clinical statistics. Supported metrics: 'medications', 'diagnoses', 'complexity', 'encounter_volume'. Returns counts suitable for charting."""
    metric = metric.strip().lower()

    async with await _get_session() as session:
        if metric == "medications":
            if _is_postgresql():
                sql = text("""
                    SELECT m->>'name' as name, COUNT(*) as value
                    FROM encounter, jsonb_array_elements(rx_json->'medicines') as m
                    GROUP BY name ORDER BY value DESC LIMIT 15
                """)
                result = await session.execute(sql)
                rows = result.all()
            else:
                stmt = select(Encounter).limit(2000)
                result = await session.execute(stmt)
                encounters = result.scalars().all()
                counts: Counter[str] = Counter()
                for enc in encounters:
                    for name in _medicine_names(enc.rx_json):
                        counts[name] += 1
                rows = [
                    type("Row", (), {"name": name, "value": value})()
                    for name, value in counts.most_common(15)
                ]
        elif metric == "diagnoses":
            sql = text("""
                SELECT diagnosis as name, COUNT(*) as value
                FROM encounter WHERE diagnosis IS NOT NULL
                GROUP BY name ORDER BY value DESC LIMIT 15
            """)
            result = await session.execute(sql)
            rows = result.all()
        elif metric == "complexity":
            sql = text("""
                SELECT COALESCE(complexity, 'Unspecified') as name, COUNT(*) as value
                FROM encounter GROUP BY name ORDER BY value DESC
            """)
            result = await session.execute(sql)
            rows = result.all()
        elif metric in ("encounter_volume", "volume", "encounters"):
            if _is_postgresql():
                sql = text("""
                    SELECT TO_CHAR(created_at, 'YYYY-MM') as name, COUNT(*) as value
                    FROM encounter GROUP BY name ORDER BY name ASC
                """)
            else:
                sql = text("""
                    SELECT strftime('%Y-%m', created_at) as name, COUNT(*) as value
                    FROM encounter GROUP BY name ORDER BY name ASC
                """)
            result = await session.execute(sql)
            rows = result.all()
        else:
            return f"Unknown metric '{metric}'. Supported: medications, diagnoses, complexity, encounter_volume"

        if not rows:
            return f"No data available for metric: {metric}."

        lines = [f"Top {metric.capitalize()} Aggregation:"]
        for r in rows:
            lines.append(f"- {r.name}: {r.value}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 5 — Generate Chart (Visualization)
# ---------------------------------------------------------------------------

@tool
async def generate_chart(chart_type: str, title: str, labels: List[str], values: List[float], drill_down_template: Optional[str] = None) -> str:
    """
    Generate a structured JSON chart schema for frontend rendering. 
    chart_type must be 'bar', 'line', or 'pie'. 
    labels and values must be equal-length lists.
    drill_down_template (optional) is a string like "Show me the patients with {}" where {} will be replaced by the clicked label.
    """
    chart_type = chart_type.strip().lower()
    if chart_type not in ("bar", "line", "pie"):
        return f"Unsupported chart_type '{chart_type}'. Use 'bar', 'line', or 'pie'."

    if len(labels) != len(values):
        return f"labels ({len(labels)}) and values ({len(values)}) must have equal length."

    # Build Recharts-compatible data array
    data = [{"name": label, "value": val} for label, val in zip(labels, values)]

    # Color palette — clinical / professional tones
    colors = [
        "#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd",
        "#818cf8", "#4f46e5", "#7c3aed", "#5b21b6",
        "#6d28d9", "#4c1d95", "#2dd4bf", "#14b8a6",
        "#0d9488", "#0f766e", "#f59e0b",
    ]

    chart_schema = {
        "__chart__": True,
        "chart_type": chart_type,
        "title": title,
        "data": data,
        "xKey": "name",
        "yKey": "value",
        "colors": colors[: len(data)],
        "drill_down_template": drill_down_template
    }

    return _json.dumps(chart_schema)


# ---------------------------------------------------------------------------
# All tools list — imported by intelligence.py
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    search_patients,
    get_patient_history,
    get_recent_encounters,
    search_clinical_records,
    aggregate_clinical_data,
    generate_chart,
]
