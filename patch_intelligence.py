import re

with open("app/api/v1/intelligence.py", "r") as f:
    content = f.read()

imports = """
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
from langgraph.prebuilt import ToolNode
from datetime import datetime, timedelta
import operator
import json
"""

content = re.sub(r'from typing import List.*?(?=router = APIRouter)', imports, content, flags=re.DOTALL)

# Let's add the AgentState and Tools before the query_intelligence endpoint
new_endpoint = """
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

@tool
def search_patients_mock(query: str) -> str:
    \"\"\"Mock tool to search patients in the database.\"\"\"
    return f"Found patient matching {query} in the registry."

@tool
def aggregate_clinical_data_mock(metric: str) -> str:
    \"\"\"Mock tool to aggregate clinical data (e.g., medications, diagnoses) for charting.\"\"\"
    return f"Aggregated data for {metric}: High complexity (12), Moderate (5)."

def get_intelligence_graph():
    tools = [search_patients_mock, aggregate_clinical_data_mock]
    tool_node = ToolNode(tools)
    
    def call_model(state: AgentState):
        llm = get_clinical_llm()
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}
        
    def should_continue(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools"
        return END
        
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()

@router.post("/query")
async def query_intelligence(payload: Dict[str, Any], current_user: User = Depends(get_current_user)):
    \"\"\"
    Query the clinical reasoning core with session persistence and real patient context using LangGraph.
    Streams SSE to the frontend.
    \"\"\"
    user_query = payload.get("query", "")
    session_id = payload.get("session_id")
    
    with get_session() as session:
        if not session_id:
            intel_session = IntelligenceSession(doctor_id=str(current_user.id), title=user_query[:50] + "...")
            session.add(intel_session)
            session.commit()
            session.refresh(intel_session)
            session_id = intel_session.id
        else:
            intel_session = session.get(IntelligenceSession, session_id)
            if not intel_session or intel_session.doctor_id != str(current_user.id):
                intel_session = IntelligenceSession(doctor_id=str(current_user.id), title=user_query[:50] + "...")
                session.add(intel_session)
                session.commit()
                session.refresh(intel_session)
                session_id = intel_session.id

        user_msg = IntelligenceMessage(session_id=session_id, role="user", content=user_query)
        session.add(user_msg)
        
        history_stmt = select(IntelligenceMessage).where(IntelligenceMessage.session_id == session_id).order_by(IntelligenceMessage.created_at.asc())
        history = session.exec(history_stmt).all()
        
        if current_user.role == "admin":
            enc_count = session.exec(select(func.count(Encounter.id))).one()
            pat_count = session.exec(select(func.count(Customer.id))).one()
            stmt = select(Customer).limit(10)
            context_type = "Global Administrative"
        elif current_user.role == "clinic_admin" and current_user.clinic_id:
            enc_count = session.exec(select(func.count(Encounter.id)).where(Encounter.clinic_id == current_user.clinic_id)).one()
            pat_count = session.exec(select(func.count(Customer.id)).where(Customer.clinic_id == current_user.clinic_id)).one()
            stmt = select(Customer).where(Customer.clinic_id == current_user.clinic_id).limit(10)
            context_type = f"Institutional (Clinic: {current_user.clinic_id})"
        else:
            enc_count = session.exec(select(func.count(Encounter.id)).where(Encounter.doctor_id == str(current_user.id))).one()
            pat_count = session.exec(select(func.count(Customer.id)).where(Customer.doctor_id == str(current_user.id))).one()
            stmt = select(Customer).where(Customer.doctor_id == str(current_user.id)).limit(10)
            context_type = "Individual Provider"

        recent_patients = session.exec(stmt).all()
        patient_list = ", ".join([p.name for p in recent_patients])

        if current_user.role == "admin":
            recent_enc_stmt = select(Encounter).order_by(Encounter.created_at.desc()).limit(40)
        elif current_user.role == "clinic_admin" and current_user.clinic_id:
            recent_enc_stmt = select(Encounter).where(Encounter.clinic_id == current_user.clinic_id).order_by(Encounter.created_at.desc()).limit(40)
        else:
            recent_enc_stmt = select(Encounter).where(Encounter.doctor_id == str(current_user.id)).order_by(Encounter.created_at.desc()).limit(40)

        recent_encounters = session.exec(recent_enc_stmt).all()
        history_lines = []
        
        customer_ids = list({e.customer_id for e in recent_encounters})
        cust_stmt = select(Customer).where(Customer.id.in_(customer_ids))
        customers = session.exec(cust_stmt).all()
        cust_map = {c.id: c.name for c in customers}
        
        for enc in recent_encounters:
            c_name = cust_map.get(enc.customer_id, "Unknown Patient")
            diag = enc.diagnosis or "Unspecified"
            rx_list = []
            if enc.rx_json and isinstance(enc.rx_json, dict) and "medicines" in enc.rx_json:
                rx_list = [m.get("name", "") for m in enc.rx_json["medicines"]]
            rx_str = ", ".join(filter(None, rx_list)) if rx_list else "None"
            history_lines.append(f"- Patient: {c_name} | Date: {enc.created_at.strftime('%Y-%m-%d')} | Diagnosis: {diag} | Meds: {rx_str}")
        
        recent_history = "\\n".join(history_lines) if history_lines else "No recent clinical history."

    system_prompt = f\"\"\"
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
    
    CRITICAL: When generating a CHART, ALWAYS aggregate the data logically (e.g. count of each medication, diagnosis frequency). NEVER plot individual patient names on the X-axis for aggregate metrics like medications given. Make the chart actually informative.
    
    Schema:
    ```json
    {{
        "narrative": "Your textual explanation here",
        "directives": ["TABLE", "CHART", "RISK_PROFILE"],
        "data": {{
            "table": {{ "headers": [...], "rows": [[...]] }},
            "chart": {{ "labels": [...], "values": [...] }},
            "risk_profiles": [...]
        }}
    }}
    ```
    Otherwise, respond with standard markdown.
    \"\"\"
    
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
            async for event in graph.astream_events({"messages": messages}, version="v2"):
                kind = event["event"]
                
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        final_response += chunk.content
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk.content})}\n\n"
                
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name})}\n\n"
                    
                elif kind == "on_tool_end":
                    tool_name = event["name"]
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name})}\n\n"
                    
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Intelligence LLM Error: {error_msg}")
            final_response = f"I am unable to provide a deep analysis at this moment due to an error: {error_msg[:100]}..."
            yield f"data: {json.dumps({'type': 'error', 'content': final_response})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
        
        # Save to DB after streaming is done
        with get_session() as db_session:
            assistant_msg = IntelligenceMessage(session_id=session_id, role="assistant", content=final_response)
            db_session.add(assistant_msg)
            
            intel_sess = db_session.get(IntelligenceSession, session_id)
            if intel_sess:
                intel_sess.updated_at = datetime.utcnow()
                db_session.add(intel_sess)
            db_session.commit()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
"""

content = re.sub(r'@router\.post\("/query"\).*', new_endpoint, content, flags=re.DOTALL)

with open("app/api/v1/intelligence.py", "w") as f:
    f.write(content)
