# Doctor Support Backend API

Base URL (local):
- `http://127.0.0.1:8000`

OpenAPI (Swagger UI):
- `http://127.0.0.1:8000/docs`

## POST `/v1/process-audio`

Process an uploaded audio file:
- Sarvam transcribes the audio by default, with Whisper as fallback
- LLM generates patient summary + RX extraction
- Formats RX into text
- Sends email via Brevo (transactional)

Request:
- Content-Type: `multipart/form-data`
- Form fields:
  - `audio` (file, required): `wav`, `mp3`, `m4a`, `ogg`, etc.
  - `to_email` (string, optional): recipient email
  - `email_subject` (string, optional): email subject

Notes:
- If `to_email` is not provided, the backend uses `BREVO_DEFAULT_TO_EMAIL`.
- If both are empty, sending email will fail.

Example:
```bash
curl -X POST "http://127.0.0.1:8000/v1/process-audio" \
  -F "audio=@/Users/sathya/Downloads/customer support/doctor support/sample_rx.wav" \
  -F "to_email=doctor@example.com" \
  -F "email_subject=Prescription Summary"
```

Response (JSON; keys may vary slightly by LangGraph/state):
- `transcript` (string)
- `cleaned_text` (string)
- `rx` (object; Prescription schema)
- `rx_text` (string; formatted RX)
- `validation_errors` (array of strings)
- `email_status` (string)
- `email_message_id` (string)

## POST `/v1/process-text`

Process an already-available transcript:
- Cleans transcript
- Generates patient summary + RX extraction
- Formats RX into text
- Sends email via Brevo (transactional)

Request:
- Content-Type: `application/json`
- Body:
```json
{
  "transcript": "Patient name Ravi Kumar...",
  "to_email": "doctor@example.com",
  "email_subject": "Prescription Summary"
}
```

Example:
```bash
curl -X POST "http://127.0.0.1:8000/v1/process-text" \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "Patient name Ravi Kumar, age 32, male. Diagnosis: fever. Prescribe paracetamol 500 mg twice daily for 3 days.",
    "to_email": "doctor@example.com",
    "email_subject": "Prescription Summary"
  }'
```

Response:
- `transcript` (string; original)
- `cleaned_text` (string)
- `rx` (object; Prescription schema)
- `rx_text` (string; formatted RX)
- `email_status` (string; usually `sent`)
- `email_message_id` (string)

## Prescription Schema (RX JSON)

The extracted structure is defined in `app/schemas/rx_schema.py`:
- `patient_name` (string|null)
- `age` (int|null)
- `gender` (string|null)
- `diagnosis` (string|null)
- `medicines` (array; required)
  - `name` (string)
  - `dosage` (string; may be empty)
  - `frequency` (string; may be empty)
  - `duration` (string; may be empty)
  - `route` (string|null)
  - `instructions` (string|null)
- `advice` (string|null)
- `follow_up` (string|null)

## Required Env Vars (Backend)

Minimum (LLM + ASR + email):
- `OPENAI_MODEL` (for Ollama: `llama3.1:8b`)
- `API_BASE_URL` (for Ollama: `http://localhost:11434/v1`)
- `OPENAI_API_KEY` (can be a dummy like `ollama` for local OpenAI-compatible servers)
- `ASR_PROVIDER=sarvam`
- `SARVAM_API_KEY`
- `SARVAM_BASE_URL` (optional; defaults to `https://api.sarvam.ai`)
- `SARVAM_SPEECH_MODEL` (optional; defaults to `saaras:v3`)
- `SARVAM_MODE` (optional; defaults to `transcribe`)
- `WHISPER_MODEL=base`
- `WHISPER_DEVICE` (optional)
- `WHISPER_COMPUTE_TYPE` (optional)
- `BREVO_API_KEY`
- `BREVO_SENDER_EMAIL`
- `BREVO_SENDER_NAME`
- `BREVO_DEFAULT_TO_EMAIL` (optional if you always pass `to_email`)

