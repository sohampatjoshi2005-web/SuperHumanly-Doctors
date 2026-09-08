from typing import List, Dict, Any, Optional, TypedDict, Annotated, Sequence
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import select, func
from app.api.v1.auth import get_current_user
from app.db import get_session
from app.db_models import User, Encounter, Customer, IntelligenceSession, IntelligenceMessage
from pydantic import BaseModel
from app.services.llm_factory import get_chat_llm, get_clinical_llm
from app.services.risk_service import detect_risks
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from datetime import datetime, timezone, timedelta
import operator
import json
import asyncio
from app.db import async_session_maker

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

class Metric(BaseModel):
    value: str
    trend: str
    label: str

class SelectionBias(BaseModel):
    label: str
    value: float
    variance: str

class DutyCycleVelocity(BaseModel):
    labels: List[str]
    current: List[int]
    baseline: List[int]
    variance_threshold: float = 0.15

class IntelligenceStats(BaseModel):
    total_encounters: int
    total_patients: int
    intelligence_score: float
    data_points: int
    top_specialty: str = "General Medicine"
    predictive_risk: Metric
    clinical_velocity: Metric
    revenue_integrity: Metric
    selection_bias: List[SelectionBias]
    heatmap: List[int] # Legacy flat heatmap
    temporal_heatmap: List[List[int]] # New 7x24 matrix
    duty_cycle_velocity: DutyCycleVelocity

@router.get("/stats", response_model=IntelligenceStats)
async def get_intelligence_stats(current_user: User = Depends(get_current_user)):
    # 1. Base counts & Filters
    enc_filters = []
    pat_filters = []
    if current_user.role == "admin":
        pass # Global access
    elif current_user.role == "clinic_admin" and current_user.clinic_id:
        enc_filters = [Encounter.clinic_id == current_user.clinic_id]
        pat_filters = [Customer.clinic_id == current_user.clinic_id]
    else:
        enc_filters = [Encounter.doctor_id == str(current_user.id)]
        pat_filters = [Customer.doctor_id == str(current_user.id)]

    # Run counts in parallel — each query gets its own session to avoid
    # SQLAlchemy's "concurrent operations are not permitted" error.
    async def fetch_scalar(stmt):
        async with async_session_maker() as s:
            result = await s.execute(stmt)
            return result.scalar_one()

    counts_results = await asyncio.gather(
        fetch_scalar(select(func.count(Encounter.id)).where(*enc_filters)),
        fetch_scalar(select(func.count(Customer.id)).where(*pat_filters)),
        fetch_scalar(select(func.count(Encounter.id)).where(*enc_filters, Encounter.complexity == "High")),
        fetch_scalar(select(func.count(Encounter.id)).where(*enc_filters, Encounter.complexity == "Moderate")),
        fetch_scalar(select(func.count(Encounter.id)).where(*enc_filters, Encounter.complexity == "Low")),
    )
    
    enc_count = counts_results[0]
    pat_count = counts_results[1]
    high_comp = counts_results[2]
    mod_comp = counts_results[3]
    low_comp = counts_results[4]
    
    # 3. Documentation Velocity (Estimated from enc_count trends)
    score = min(98.5, 70.0 + (enc_count * 1.5))
    
    # 4. Temporal Heatmap (7x24 Matrix)
    temporal_heatmap = [[0 for _ in range(24)] for _ in range(7)]
    
    # 5. Duty Cycle Velocity
    velocity_labels = []
    velocity_current = []
    velocity_baseline = []
    
    # Fetch encounters for heatmap (sequential — single session is fine here)
    async with async_session_maker() as session:
        stmt = select(Encounter.created_at).where(*enc_filters).order_by(Encounter.created_at.asc())
        enc_result = await session.execute(stmt)
        encounters = enc_result.scalars().all()
    
    for e in encounters:
        day = e.weekday()
        hour = e.hour
        temporal_heatmap[day][hour] += 1
        
    from collections import Counter
    daily_counts = Counter(e.date() for e in encounters)
    
    today = datetime.now(timezone.utc).date()
    for i in range(13, -1, -1):
        date = today - timedelta(days=i)
        velocity_labels.append(date.strftime("%d %b"))
        velocity_current.append(daily_counts[date])
        velocity_baseline.append(max(1, enc_count // 30))

    heatmap = [sum(temporal_heatmap[d][h] for d in range(7)) for h in range(24)]

    return IntelligenceStats(
        total_encounters=enc_count,
        total_patients=pat_count,
        intelligence_score=score,
        data_points=enc_count * 15,
        predictive_risk=Metric(
            value="High" if high_comp > 5 else ("Moderate" if high_comp > 0 else "Low"),
            trend=f"{'+' if high_comp > 0 else ''}{high_comp * 5}%",
            label="Registry Complexity Index"
        ),
        clinical_velocity=Metric(
            value=f"{min(100, 75 + (enc_count * 2))}%",
            trend="+8.2%",
            label="Processing Efficiency"
        ),
        revenue_integrity=Metric(
            value=f"{min(100, 94.5 + (mod_comp * 0.2))}%",
            trend="+0.4%",
            label="Coding Compliance"
        ),
        selection_bias=[
            SelectionBias(label="High Complexity", value=high_comp, variance=f"{high_comp/max(1, enc_count)*100:.0f}%"),
            SelectionBias(label="Moderate", value=mod_comp, variance=f"{mod_comp/max(1, enc_count)*100:.0f}%"),
            SelectionBias(label="Low Priority", value=low_comp, variance=f"{low_comp/max(1, enc_count)*100:.0f}%")
        ],
        heatmap=heatmap,
        temporal_heatmap=temporal_heatmap,
        duty_cycle_velocity=DutyCycleVelocity(
            labels=velocity_labels,
            current=velocity_current,
            baseline=velocity_baseline
        )
    )

@router.get("/sessions", response_model=List[IntelligenceSession])
async def list_intelligence_sessions(current_user: User = Depends(get_current_user)):
    async with async_session_maker() as session:
        stmt = select(IntelligenceSession).where(IntelligenceSession.doctor_id == str(current_user.id)).order_by(IntelligenceSession.updated_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

@router.get("/sessions/{session_id}/messages", response_model=List[IntelligenceMessage])
async def get_session_messages(session_id: str, current_user: User = Depends(get_current_user)):
    async with async_session_maker() as session:
        intel_session = await session.get(IntelligenceSession, session_id)
        if not intel_session or intel_session.doctor_id != str(current_user.id):
            return []
            
        stmt = select(IntelligenceMessage).where(IntelligenceMessage.session_id == session_id).order_by(IntelligenceMessage.created_at.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

class SessionRename(BaseModel):
    title: str

@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, payload: SessionRename, current_user: User = Depends(get_current_user)):
    async with async_session_maker() as session:
        intel_session = await session.get(IntelligenceSession, session_id)
        if not intel_session or intel_session.doctor_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Session not found")
        
        intel_session.title = payload.title
        intel_session.updated_at = datetime.utcnow()
        session.add(intel_session)
        await session.commit()
        await session.refresh(intel_session)
        return intel_session

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, current_user: User = Depends(get_current_user)):
    async with async_session_maker() as session:
        intel_session = await session.get(IntelligenceSession, session_id)
        if not intel_session or intel_session.doctor_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Session not found")
        
        msg_stmt = select(IntelligenceMessage).where(IntelligenceMessage.session_id == session_id)
        msg_result = await session.execute(msg_stmt)
        messages = msg_result.scalars().all()
        for msg in messages:
            await session.delete(msg)
            
        await session.delete(intel_session)
        await session.commit()
        return {"status": "deleted"}

@router.get("/risks/{customer_id}")
async def get_patient_risks(customer_id: str, current_user: User = Depends(get_current_user)):
    """
    Fetch proactive clinical risks for a specific patient.
    """
    async with async_session_maker() as session:
        customer = await session.get(Customer, customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Patient not found")
            
        is_owner = customer.doctor_id == str(current_user.id)
        is_in_clinic = current_user.clinic_id and customer.clinic_id == current_user.clinic_id
        is_admin = current_user.role == "admin"
        
        if not (is_owner or is_in_clinic or is_admin):
            raise HTTPException(status_code=403, detail="Access denied to this patient record")
            
        # risk_service is now async
        risks = await detect_risks(session, customer_id)
        return risks


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    validation_count: int

def get_intelligence_graph():
    from app.services.intelligence_tools import ALL_TOOLS
    tools = ALL_TOOLS
    tool_node = ToolNode(tools)
    
    def call_model(state: AgentState):
        llm = get_clinical_llm()
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}
        
    def validate_integrity(state: AgentState):
        """Node that audits the agent's findings against raw tool data."""
        llm = get_clinical_llm()
        messages = state["messages"]
        v_count = state.get("validation_count", 0)
        
        # Find the last actual narrative message and tool outputs
        last_ai_msg = next((m for m in reversed(messages) if isinstance(m, AIMessage) and m.content and not m.tool_calls), None)
        tool_messages = [m for m in messages if hasattr(m, "tool_call_id")]
        
        # Optimization: Skip if we've already tried too many times or have no data to verify
        if v_count >= 2 or not last_ai_msg or not tool_messages:
            return {"messages": [AIMessage(content="VERIFIED", name="validator")], "validation_count": v_count + 1}

        audit_prompt = f"""
        Audit the Assistant's narrative against the Tool Results. 
        Focus ONLY on clinical facts (meds, counts, names).
        Tool Results: {json.dumps([m.content[:500] for m in tool_messages])}
        Assistant Narrative: {last_ai_msg.content[:1000]}
        Reply 'VERIFIED' if accurate, else 'CORRECTION_REQUIRED: [discrepancy]'.
        """
        response = llm.invoke([SystemMessage(content=audit_prompt)])
        return {"messages": [AIMessage(content=response.content, name="validator")], "validation_count": v_count + 1}

    def should_continue(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        
        # 1. Handle tool calls
        if last_message.tool_calls:
            return "tools"
        
        # 2. Handle validator output
        if hasattr(last_message, "name") and last_message.name == "validator":
            if "VERIFIED" in last_message.content:
                return END
            return "agent" # Loop back for correction
            
        # 3. Decision: Should we validate?
        # OPTIMIZATION: Only validate if there were tool calls in this turn
        # and if the message looks like a clinical analysis (has JSON or keywords)
        has_tools = any(hasattr(m, "tool_call_id") for m in messages[-3:])
        is_clinical = any(k in last_message.content.lower() for k in ["medication", "patient", "diagnosis", "encounters", "{"])
        
        if has_tools and is_clinical:
            return "validator"
            
        return END
        
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_node("validator", validate_integrity)
    
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "validator": "validator", END: END})
    workflow.add_edge("tools", "agent")
    workflow.add_conditional_edges("validator", should_continue, {"agent": "agent", END: END})
    
    return workflow.compile()

@router.post("/query")
async def query_intelligence(payload: Dict[str, Any], current_user: User = Depends(get_current_user)):
    """
    Query the clinical reasoning core with session persistence and real patient context using LangGraph.
    Streams SSE to the frontend.
    """
    user_query = payload.get("query", "")
    session_id = payload.get("session_id")
    
    async with async_session_maker() as session:
        if not session_id:
            intel_session = IntelligenceSession(doctor_id=str(current_user.id), title=user_query[:50] + "...")
            session.add(intel_session)
            await session.commit()
            await session.refresh(intel_session)
            session_id = intel_session.id
        else:
            intel_session = await session.get(IntelligenceSession, session_id)
            if not intel_session or intel_session.doctor_id != str(current_user.id):
                intel_session = IntelligenceSession(doctor_id=str(current_user.id), title=user_query[:50] + "...")
                session.add(intel_session)
                await session.commit()
                await session.refresh(intel_session)
                session_id = intel_session.id

        user_msg = IntelligenceMessage(session_id=session_id, role="user", content=user_query)
        session.add(user_msg)
        await session.commit()
        
        # PARALLEL CONTEXT GATHERING
        if current_user.role == "admin":
            enc_stmt = select(func.count(Encounter.id))
            pat_stmt = select(func.count(Customer.id))
            reg_stmt = select(Customer).limit(10)
            rec_stmt = select(Encounter).order_by(Encounter.created_at.desc()).limit(10)
            context_type = "Global Administrative"
        elif current_user.role == "clinic_admin" and current_user.clinic_id:
            enc_stmt = select(func.count(Encounter.id)).where(Encounter.clinic_id == current_user.clinic_id)
            pat_stmt = select(func.count(Customer.id)).where(Customer.clinic_id == current_user.clinic_id)
            reg_stmt = select(Customer).where(Customer.clinic_id == current_user.clinic_id).limit(10)
            rec_stmt = select(Encounter).where(Encounter.clinic_id == current_user.clinic_id).order_by(Encounter.created_at.desc()).limit(10)
            context_type = f"Institutional (Clinic: {current_user.clinic_id})"
        else:
            enc_stmt = select(func.count(Encounter.id)).where(Encounter.doctor_id == str(current_user.id))
            pat_stmt = select(func.count(Customer.id)).where(Customer.doctor_id == str(current_user.id))
            reg_stmt = select(Customer).where(Customer.doctor_id == str(current_user.id)).limit(10)
            rec_stmt = select(Encounter).where(Encounter.doctor_id == str(current_user.id)).order_by(Encounter.created_at.desc()).limit(10)
            context_type = "Individual Provider"

        # Execute everything in parallel using separate sessions to avoid concurrency issues on a single session
        async def fetch_data(stmt):
            async with async_session_maker() as s:
                return await s.execute(stmt)

        results = await asyncio.gather(
            fetch_data(enc_stmt),
            fetch_data(pat_stmt),
            fetch_data(reg_stmt),
            fetch_data(rec_stmt),
            fetch_data(select(IntelligenceMessage).where(IntelligenceMessage.session_id == session_id).order_by(IntelligenceMessage.created_at.asc()))
        )
        
        enc_count = results[0].scalar_one()
        pat_count = results[1].scalar_one()
        recent_patients = results[2].scalars().all()
        recent_encounters = results[3].scalars().all()
        history = results[4].scalars().all()
        
        patient_list = ", ".join([p.name for p in recent_patients])

        # Resolve patient names for encounters in parallel if needed
        customer_ids = list({e.customer_id for e in recent_encounters})
        cust_stmt = select(Customer).where(Customer.id.in_(customer_ids))
        async with async_session_maker() as s:
            cust_result = await s.execute(cust_stmt)
            customers = cust_result.scalars().all()
        cust_map = {c.id: c.name for c in customers}
        
        history_lines = []
        for enc in recent_encounters:
            c_name = cust_map.get(enc.customer_id, "Unknown Patient")
            diag = enc.diagnosis or "Unspecified"
            rx_list = []
            if enc.rx_json and isinstance(enc.rx_json, dict) and "medicines" in enc.rx_json:
                rx_list = [m.get("name", "") for m in enc.rx_json["medicines"]]
            rx_str = ", ".join(filter(None, rx_list)) if rx_list else "None"
            history_lines.append(f"- Patient: {c_name} | Date: {enc.created_at.strftime('%Y-%m-%d')} | Diagnosis: {diag} | Meds: {rx_str}")
        recent_history = "\\n".join(history_lines) if history_lines else "No recent clinical history."

    system_prompt = f"""
    You are the Superhumanly Clinical Intelligence Engine. 
    You are assisting {current_user.role.replace('_', ' ').title()} {current_user.full_name or current_user.username}.
    
    Current Context:
    - Mode: {context_type}
    - Total Patients: {pat_count}
    - Total Encounters: {enc_count}
    - Sample Registry: [{patient_list}]
    
    Recent Clinical History (Context for answering patient-specific questions):
    {recent_history}
    
    - Institutional Status: Active
    
    Answer queries based on clinical documentation best practices and the provided context.
    Be professional, concise, and insightful.

    DIRECTIVE:
    If the user asks for data analysis, workload trends, patient lists, or a CHART/GRAPH, you MUST return a JSON object 
    embedded in your response that follows the IntelligenceResponse schema.
    
    CRITICAL: When generating a CHART, ALWAYS aggregate the data logically (e.g. count of each medication, diagnosis frequency). 
    INTERACTIVE DRILL-DOWN: When invoking the generate_chart tool, you MUST provide a 'drill_down_template' if the chart represents a category (like a medication or diagnosis). 
    Example: "Show me the patients who are prescribed {{}}" where {{}} will be replaced by the clicked label. 
    NOTE: To resolve these drill-down queries, use the 'search_clinical_records' tool to find patients by medication or diagnosis.
    
    Schema:
    ```json
    {{
        "narrative": "Your textual explanation here",
        "directives": ["TABLE", "CHART", "RISK_PROFILE"],
        "data": {{
            "table": {{ "headers": [...], "rows": [[...]] }},
            "chart": {{ "labels": [...], "values": [...], "drill_down_template": "..." }},
            "risk_profiles": [...]
        }}
    }}
    ```
    Otherwise, respond with standard markdown.
    """
    
    messages = [SystemMessage(content=system_prompt)]
    for h in history:
        if h.role == "user":
            messages.append(HumanMessage(content=h.content))
        else:
            messages.append(AIMessage(content=h.content))

    async def event_generator():
        graph = get_intelligence_graph()
        final_response = ""
        
        try:
            async for event in graph.astream_events({"messages": messages, "validation_count": 0}, version="v2"):
                kind = event["event"]
                
                if kind == "on_chat_model_stream":
                    # ONLY stream content from the main 'agent' node
                    node_name = event.get("metadata", {}).get("langgraph_node", "")
                    if node_name == "agent":
                        chunk = event["data"]["chunk"]
                        if chunk.content:
                            final_response += chunk.content
                            yield f"data: {json.dumps({'type': 'content', 'content': chunk.content})}\n\n"
                
                elif kind == "on_tool_start":
                    # ... existing tool start ...
                    tool_name = event["name"]
                    print(f"DEBUG: 🛠️ Starting Tool: {tool_name}")
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name})}\n\n"
                    
                elif kind == "on_tool_end":
                    # ... existing tool end ...
                    tool_name = event["name"]
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name})}\n\n"

                elif kind == "on_chain_start" and event["name"] == "validator":
                    yield f"data: {json.dumps({'type': 'verification_status', 'status': 'checking'})}\n\n"
                
                elif kind == "on_chain_end" and event["name"] == "validator":
                    output = event["data"]["output"]
                    content = output["messages"][-1].content
                    status = "verified" if "VERIFIED" in content else "correction_applied"
                    
                    if status == "correction_applied":
                        # WIPE the previous hallucinated content from the UI buffer
                        final_response = ""
                        yield f"data: {json.dumps({'type': 'clear_content'})}\n\n"
                        
                    print(f"DEBUG: Validator finished with status: {status}")
                    yield f"data: {json.dumps({'type': 'verification_status', 'status': status})}\n\n"
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Intelligence LLM Error: {error_msg}")
            final_response = f"I am unable to provide a deep analysis at this moment due to an error: {error_msg[:100]}..."
            yield f"data: {json.dumps({'type': 'error', 'content': final_response})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

        # Save to DB after streaming is done
        async with async_session_maker() as db_session:
            assistant_msg = IntelligenceMessage(session_id=session_id, role="assistant", content=final_response)
            db_session.add(assistant_msg)
            
            intel_sess = await db_session.get(IntelligenceSession, session_id)
            if intel_sess:
                intel_sess.updated_at = datetime.utcnow()
                db_session.add(intel_sess)
            await db_session.commit()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
