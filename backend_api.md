# Doctor Support Backend API (Frontend Notes)

Base URL (EC2):
- `http://<EC2_PUBLIC_IP>:8000`

Swagger/OpenAPI:
- `http://<EC2_PUBLIC_IP>:8000/docs`

## CORS (Frontend Access)

If your frontend runs separately (example: Vite on `http://localhost:5173`) you must allow that origin.

Env var:
- `CORS_ALLOW_ORIGINS` (comma-separated)

Example:
```bash
export CORS_ALLOW_ORIGINS="http://localhost:5173,http://127.0.0.1:5173,https://superhumanlydoctors.io"
```

## Database APIs

These endpoints support the per-customer storage layer (customers + encounter history).

### GET `/v1/customers`

Example:
```bash
curl "http://<EC2_PUBLIC_IP>:8000/v1/customers"
```

### POST `/v1/customers`

Request JSON:
```json
{ "name": "Sathya" }
```

Example:
```bash
curl -X POST "http://<EC2_PUBLIC_IP>:8000/v1/customers" \
  -H "Content-Type: application/json" \
  -d '{"name":"Sathya"}'
```

### GET `/v1/customers/{customer_id}`

Fetch one customer by id.

### GET `/v1/customers/{customer_id}/encounters`

List encounters for a customer (most recent first).

### GET `/v1/encounters/{encounter_id}`

Fetch one encounter by id (includes transcript, summaries, rx JSON/text, email status).

## POST `/v1/process-audio`

Upload audio, get transcript + extracted RX + formatted RX, and (currently) email is sent by backend.

Notes:
- Email sending is best-effort. If Brevo isn't configured or recipient is missing, the API still returns transcript/RX and sets `email_status` to `skipped` with `email_error`.
- “Live recording” in the frontend uses the same endpoint: record mic → send as multipart `audio` file to `/v1/process-audio`.
- Frontend tip: when sending `FormData`, **do not** manually set the `Content-Type` header. Let the browser set the `multipart/form-data; boundary=...` header.

Request:
- Content-Type: `multipart/form-data`
- Fields:
  - `audio` (file, required)
  - `to_email` (string, optional)  
    If omitted, backend uses `BREVO_DEFAULT_TO_EMAIL`. If both are empty, send will fail.
  - `email_subject` (string, optional)

Example:
```bash
curl -X POST "http://<EC2_PUBLIC_IP>:8000/v1/process-audio" \
  -F "audio=@/path/to/audio.wav" \
  -F "to_email=doctor@example.com" \
  -F "email_subject=Prescription Summary"
```

Response (shape):
- `transcript` (string)
- `cleaned_text` (string)
- `rx` (object; Prescription schema)
- `rx_text` (string)
- `validation_errors` (string[])
- `email_status` (string)
- `email_message_id` (string)
- `email_error` (string|null; when `email_status` is `skipped` or `failed`)

## POST `/v1/process-text`

Send transcript text (no audio upload).

Notes:
- Email sending is best-effort. If Brevo isn't configured or recipient is missing, the API still returns transcript/RX and sets `email_status` to `skipped`.
- This endpoint currently does **not** return an LLM patient summary (it can be added if required).

Request:
- Content-Type: `application/json`
```json
{
  "transcript": "string",
  "to_email": "doctor@example.com",
  "email_subject": "Prescription Summary"
}
```

Example:
```bash
curl -X POST "http://<EC2_PUBLIC_IP>:8000/v1/process-text" \
  -H "Content-Type: application/json" \
  -d '{"transcript":"Patient has fever...","to_email":"doctor@example.com"}'
```

Response:
- `transcript` (string)
- `cleaned_text` (string)
- `patient_summary` (string; LLM-generated)
- `rx` (object; Prescription schema)
- `rx_text` (string)
- `email_status` (string)
- `email_message_id` (string)
- `email_error` (string|null)

## Prescription Schema (RX JSON)

Top-level:
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

## Environment

- `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME`, `BREVO_DEFAULT_TO_EMAIL`
- `ASR_PROVIDER` (defaults to `sarvam`), `SARVAM_API_KEY`, `SARVAM_BASE_URL`, `SARVAM_SPEECH_MODEL`, `SARVAM_MODE`
- `WHISPER_MODEL` (and optional `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`) for fallback

### LLM Provider

This app supports multiple LLM backends via `LLM_PROVIDER`:

- **Bedrock (recommended on EC2)**
  - `LLM_PROVIDER=bedrock`
  - `AWS_BEARER_TOKEN_BEDROCK` (Bedrock API key token) OR use an EC2 IAM role with Bedrock permissions
  - `BEDROCK_REGION` (example: `us-east-2`)
  - `BEDROCK_MODEL_ID`
    - For **cross-region-only** Anthropic models (e.g. Claude Haiku 4.5), use an **Inference Profile ARN** as the model identifier.
    - Example: `arn:aws:bedrock:us-east-2:123456789012:application-inference-profile/abc123`
  - `BEDROCK_PROVIDER=anthropic` (needed when using an ARN model id)

- **OpenAI-compatible (OpenAI / Ollama / vLLM)**
  - `LLM_PROVIDER=openai`
  - `OPENAI_API_KEY`, `OPENAI_MODEL`, `API_BASE_URL` (optional; for Ollama/OpenAI-compatible)

- `DATABASE_URL` (optional; defaults to SQLite `sqlite:///./doctor_support.db`)
