import tempfile
import streamlit as st
import httpx

from app.services.transcription_service import transcribe_audio
from app.services.rx_service import clean_transcript, extract_prescription
from app.services.summary_service import generate_patient_summary
from app.services.formatting_service import format_prescription_text
from app.core.langgraph.tools.mailer import send_rx_email
from app.db_models import Encounter
from app.services.storage_service import (
    create_customer,
    get_encounter,
    list_customers,
    list_encounters,
    update_encounter_email,
)
from app.core.config import settings

API_URL = settings.api_base_url or "http://localhost:8000"
if not API_URL.endswith("/v1"):
    API_URL = f"{API_URL.rstrip('/')}/v1"

st.set_page_config(page_title="Doctor Support", layout="centered")

# --- Auth State ---
if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None

def handle_logout():
    st.session_state.token = None
    st.session_state.user = None
    st.rerun()

st.sidebar.title("Doctor Portal")

if not st.session_state.token:
    auth_mode = st.sidebar.radio("Select Mode", ["Login", "Sign Up"])
    
    if auth_mode == "Login":
        st.sidebar.subheader("Login")
        username = st.sidebar.text_input("Username")
        email = st.sidebar.text_input("Email")
        password = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            try:
                response = httpx.post(
                    f"{API_URL}/auth/login", 
                    json={"username": username, "email": email, "password": password},
                    timeout=10.0
                )
                if response.status_code == 200:
                    st.session_state.token = response.json()["access_token"]
                    st.session_state.user = username
                    st.sidebar.success(f"Welcome, {username}!")
                    st.rerun()
                else:
                    error_msg = response.json().get("detail", "Invalid username, email, or password")
                    st.sidebar.error(error_msg)
            except Exception as e:
                st.sidebar.error(f"Connection error: {e}")
    else:
        st.sidebar.subheader("Register")
        new_username = st.sidebar.text_input("Username")
        new_email = st.sidebar.text_input("Email")
        new_password = st.sidebar.text_input("Password", type="password")
        new_name = st.sidebar.text_input("Full Name")
        if st.sidebar.button("Register"):
            try:
                response = httpx.post(
                    f"{API_URL}/auth/register",
                    json={
                        "username": new_username, 
                        "email": new_email, 
                        "password": new_password, 
                        "full_name": new_name
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    st.session_state.token = response.json()["access_token"]
                    st.session_state.user = new_username
                    st.sidebar.success("Account created!")
                    st.rerun()
                else:
                    error_msg = response.json().get("detail", "Registration failed")
                    st.sidebar.error(error_msg)
            except Exception as e:
                st.sidebar.error(f"Connection error: {e}")
    
    st.title("Welcome to Doctor Support")
    st.info("Please login or sign up in the sidebar to access the clinical tools.")
    st.stop()

# --- Authenticated View ---
st.sidebar.write(f"Logged in as **{st.session_state.user}**")
if st.sidebar.button("Logout"):
    handle_logout()

st.sidebar.divider()
st.title("Doctor Support")

st.sidebar.header("Customers")
# ... (rest of the code follows)
customers = list_customers()
customer_label_to_id = {f"{c.name} ({c.id[:8]})": c.id for c in customers}
selected_customer_label = st.sidebar.selectbox(
    "Select customer",
    options=["(none)"] + list(customer_label_to_id.keys()),
)
selected_customer_id = None if selected_customer_label == "(none)" else customer_label_to_id[selected_customer_label]

new_customer_name = st.sidebar.text_input("New customer name")
if st.sidebar.button("Create customer"):
    if not new_customer_name.strip():
        st.sidebar.error("Customer name is required.")
    else:
        created = create_customer(new_customer_name)
        st.sidebar.success(f"Created: {created.name}")
        st.rerun()

st.sidebar.divider()
st.sidebar.header("History")
encounter_label_to_id = {}
selected_encounter_id = None
if selected_customer_id:
    encounters = list_encounters(selected_customer_id)
    encounter_label_to_id = {
        f"{e.created_at.isoformat()} ({e.id[:8]})": e.id for e in encounters
    }
    selected_encounter_label = st.sidebar.selectbox(
        "Load encounter",
        options=["(none)"] + list(encounter_label_to_id.keys()),
    )
    selected_encounter_id = None if selected_encounter_label == "(none)" else encounter_label_to_id[selected_encounter_label]
    if st.sidebar.button("Load"):
        if selected_encounter_id:
            enc = get_encounter(selected_encounter_id)
            if enc:
                st.session_state.transcript = enc.transcript
                st.session_state.rx_text = enc.rx_text
                st.session_state.rx_text_edit = enc.rx_text
                st.session_state.patient_summary = enc.patient_summary
                st.session_state.transcript_view = enc.transcript
                st.session_state.patient_summary_view = enc.patient_summary
                st.session_state.rx_json = enc.rx_json
                st.session_state.validation_errors = []
                st.rerun()
            else:
                st.sidebar.error("Encounter not found.")
if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "rx_text" not in st.session_state:
    st.session_state.rx_text = ""
if "rx_json" not in st.session_state:
    st.session_state.rx_json = None
if "validation_errors" not in st.session_state:
    st.session_state.validation_errors = []
if "patient_summary" not in st.session_state:
    st.session_state.patient_summary = ""
if "transcript_view" not in st.session_state:
    st.session_state.transcript_view = ""
if "patient_summary_view" not in st.session_state:
    st.session_state.patient_summary_view = ""
if "rx_text_edit" not in st.session_state:
    st.session_state.rx_text_edit = ""
if "last_audio_filename" not in st.session_state:
    st.session_state.last_audio_filename = None
if "last_encounter_id" not in st.session_state:
    st.session_state.last_encounter_id = None


def generate_from_transcript(raw_transcript: str):
    cleaned = clean_transcript(raw_transcript)
    patient_summary = generate_patient_summary(cleaned)
    rx = extract_prescription(cleaned)
    rx_text = format_prescription_text(rx)
    st.session_state.transcript = cleaned
    st.session_state.rx_text = rx_text
    st.session_state.rx_json = rx
    st.session_state.patient_summary = patient_summary
    # Keep widgets in sync; Streamlit keys override `value=` if present.
    st.session_state.transcript_view = cleaned
    st.session_state.patient_summary_view = patient_summary
    st.session_state.rx_text_edit = rx_text
    # lightweight validation so the UI can guide edits
    from app.utils.safety_checks import find_missing_fields

    st.session_state.validation_errors = find_missing_fields(rx)

    # Persist the encounter if a customer is selected.
    if selected_customer_id:
        encounter = Encounter(
            customer_id=selected_customer_id,
            audio_filename=st.session_state.last_audio_filename,
            transcript=cleaned,
            patient_summary=patient_summary,
            rx_json=rx.model_dump(),
            rx_text=rx_text,
        )
        from app.services.storage_service import create_encounter

        created = create_encounter(encounter)
        st.session_state.last_encounter_id = created.id

tab_workflow, tab_database = st.tabs(["Workflow", "Database"])

with tab_workflow:
    mode = st.radio("Input Type", ["Audio", "Text"], horizontal=True, key="input_type")

    to_email = st.text_input("Send to email (optional)", key="to_email")
    email_subject = st.text_input("Email subject", value="Prescription Summary", key="email_subject")

    if mode == "Audio":
        audio_source = st.radio(
            "Audio source",
            ["Upload file", "Record mic"],
            horizontal=True,
            key="audio_source",
        )

        audio_file = None
        recorded_audio = None
        if audio_source == "Upload file":
            audio_file = st.file_uploader("Upload audio", type=["wav", "mp3", "m4a", "ogg"])
        else:
            if hasattr(st, "audio_input"):
                recorded_audio = st.audio_input("Record audio", key="record_audio")
            else:
                st.warning(
                    "Live recording needs a newer Streamlit that supports `st.audio_input`. "
                    "Upgrade Streamlit and reload."
                )

        if st.button("Generate Summary"):
            if audio_source == "Upload file":
                if not audio_file:
                    st.error("Please upload an audio file.")
                    st.stop()

                st.session_state.last_audio_filename = audio_file.name
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{audio_file.name}") as tmp:
                    tmp.write(audio_file.read())
                    audio_path = tmp.name
            else:
                if not recorded_audio:
                    st.error("Please record audio.")
                    st.stop()

                # recorded_audio is an UploadedFile-like object in newer Streamlit versions
                data = recorded_audio.getvalue() if hasattr(recorded_audio, "getvalue") else recorded_audio
                name = getattr(recorded_audio, "name", None) or "recording.wav"
                st.session_state.last_audio_filename = name
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{name}") as tmp:
                    tmp.write(data)
                    audio_path = tmp.name

            with st.spinner("Transcribing + summarizing..."):
                transcript = transcribe_audio(audio_path)
                generate_from_transcript(transcript)

    else:
        transcript_input = st.text_area("Paste transcript", height=200)

        if st.button("Generate Summary"):
            if not transcript_input.strip():
                st.error("Please paste a transcript.")
            else:
                st.session_state.last_audio_filename = None
                with st.spinner("Summarizing..."):
                    generate_from_transcript(transcript_input)

    st.subheader("Transcript")
    st.write(st.session_state.transcript_view)

    st.subheader("Patient Summary")
    st.write(st.session_state.patient_summary_view)

    st.subheader("Prescription Summary (editable)")
    rx_text_edit = st.text_area(
        "Prescription Summary",
        value=st.session_state.rx_text_edit,
        height=220,
        label_visibility="collapsed",
        key="rx_text_edit",
    )

    if st.session_state.rx_json is not None:
        if st.session_state.validation_errors:
            st.warning("Missing fields: " + ", ".join(st.session_state.validation_errors))
        st.subheader("Prescription JSON")
        if hasattr(st.session_state.rx_json, "model_dump"):
            st.json(st.session_state.rx_json.model_dump())
        else:
            st.json(st.session_state.rx_json)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Regenerate Summary"):
            if st.session_state.transcript.strip():
                with st.spinner("Regenerating..."):
                    generate_from_transcript(st.session_state.transcript)
            else:
                st.error("Transcript is empty.")

    with col2:
        if st.button("Send Email"):
            if not rx_text_edit.strip():
                st.error("Summary is empty.")
            else:
                with st.spinner("Sending email..."):
                    message_id = send_rx_email(
                        subject=email_subject or "Prescription Summary",
                        text_body=rx_text_edit.strip(),
                        to_email=to_email or None,
                    )
                if st.session_state.last_encounter_id:
                    update_encounter_email(
                        st.session_state.last_encounter_id,
                        to_email=to_email or None,
                        subject=email_subject or "Prescription Summary",
                        status="sent",
                        message_id=message_id,
                    )
                st.success("Email sent.")
                st.caption(f"Message ID: {message_id}")

with tab_database:
    st.subheader("Database Overview")
    st.write(f"Total customers: {len(customers)}")
    if selected_customer_id:
        st.write(f"Selected customer: {selected_customer_label}")
        customer_encounters = list_encounters(selected_customer_id)
        st.write(f"Encounters: {len(customer_encounters)}")
    else:
        st.info("Select a customer in the sidebar to view their history.")

    st.subheader("Customers")
    if customers:
        st.dataframe(
            [{"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()} for c in customers],
            use_container_width=True,
        )
    else:
        st.write("No customers yet.")

    st.subheader("Encounters (Selected Customer)")
    if selected_customer_id:
        encounters = list_encounters(selected_customer_id)
        if encounters:
            enc_label_to_id = {f"{e.created_at.isoformat()} ({e.id[:8]})": e.id for e in encounters}
            enc_label = st.selectbox("Select encounter", options=list(enc_label_to_id.keys()))
            enc_id = enc_label_to_id[enc_label]
            enc = get_encounter(enc_id)
            if enc:
                st.write(f"Encounter ID: {enc.id}")
                st.write(f"Created at: {enc.created_at.isoformat()}")
                if enc.audio_filename:
                    st.write(f"Audio filename: {enc.audio_filename}")
                st.subheader("Transcript")
                st.write(enc.transcript)
                st.subheader("Patient Summary")
                st.write(enc.patient_summary)
                st.subheader("Prescription Summary")
                st.code(enc.rx_text, language="text")
                st.subheader("RX JSON")
                st.json(enc.rx_json or {})
                st.subheader("Email")
                st.write(f"To: {enc.email_to or ''}")
                st.write(f"Subject: {enc.email_subject or ''}")
                st.write(f"Status: {enc.email_status or ''}")
                st.write(f"Message ID: {enc.email_message_id or ''}")
        else:
            st.write("No encounters for this customer yet.")
