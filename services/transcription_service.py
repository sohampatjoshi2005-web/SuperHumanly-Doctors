from __future__ import annotations

from pathlib import Path
from typing import Iterable

import httpx
import logging

logger = logging.getLogger(__name__)

# Connection pooled thread-safe client for warm TCP socket reuse
_client = httpx.Client(
    timeout=httpx.Timeout(60.0, connect=10.0),
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=50)
)

from app.core.config import settings
from app.services.llm_factory import get_chat_llm
from langchain_core.messages import HumanMessage, SystemMessage


def _parse_glossary(raw_glossary: str) -> list[str]:
    return [term.strip() for term in raw_glossary.split(",") if term.strip()]


def _join_segments(segments: Iterable[object]) -> str:
    return " ".join(getattr(seg, "text", "").strip() for seg in segments).strip()


def _extract_transcript_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if isinstance(payload, dict):
        for key in ("transcript", "text", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for attribute in ("transcript", "text", "content"):
        value = getattr(payload, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return str(payload).strip()


def _transcribe_with_sarvam(audio_path: str, language: str | None = None) -> str:
    if not settings.sarvam_api_key:
        raise RuntimeError("SARVAM_API_KEY is not set")

    base_url = (settings.sarvam_base_url or "https://api.sarvam.ai").rstrip("/")
    
    # Skip fast API for files larger than 1MB (approx 60s of audio)
    file_size = Path(audio_path).stat().st_size
    if file_size > 1024 * 1024:
        return _transcribe_with_sarvam_async(audio_path, language)

    endpoint = f"{base_url}/speech-to-text"

    with open(audio_path, "rb") as audio_file:
        files = {
            "file": (Path(audio_path).name, audio_file, "application/octet-stream"),
        }
        data = {
            "model": settings.sarvam_speech_model,
            "mode": settings.sarvam_mode,
        }
        lang_to_use = language if language else settings.whisper_language
        if lang_to_use and lang_to_use.lower() != "unknown":
            data["language_code"] = lang_to_use

        response = _client.post(
            endpoint,
            headers={"api-subscription-key": settings.sarvam_api_key},
            data=data,
            files=files,
            timeout=180.0,
        )

    if response.status_code == 400 and "exceeds the maximum limit" in response.text:
        logger.info("🕒 Audio too long for fast API, switching to Sarvam Batch API...")
        return _transcribe_with_sarvam_async(audio_path, language)

    if response.status_code != 200:
        logger.error(f"❌ Sarvam API Error ({response.status_code}): {response.text}")
        response.raise_for_status()

    payload = response.json()
    transcript = _extract_transcript_text(payload)
    if not transcript:
        raise RuntimeError("Sarvam transcription returned an empty transcript")
    return transcript


def _transcribe_with_sarvam_async(audio_path: str, language: str | None = None) -> str:
    """
    Handles long audio files using Sarvam's official multi-step Batch Job API.
    """
    import time
    base_url = f"{settings.sarvam_base_url}/speech-to-text/job/v1"
    headers = {"api-subscription-key": settings.sarvam_api_key}
    
    # 1. Create a Job
    create_response = _client.post(
        base_url,
        headers=headers,
        json={
            "job_parameters": {
                "model": settings.sarvam_speech_model,
                "language_code": language if language else "en-IN",
                "mode": "transcribe",
                "with_timestamps": False
            },
            "file_names": [Path(audio_path).name]
        },
        timeout=30.0
    )
    if not create_response.is_success:
        logger.error(f"❌ Sarvam Job Creation Error: {create_response.text}")
        create_response.raise_for_status()
        
    job_data = create_response.json()
    job_id = job_data.get("job_id")
    if not job_id:
        logger.error(f"❌ Sarvam Job Error: Missing job_id in response: {job_data}")
        raise ValueError("Invalid response from Sarvam Job Creation")

    # 1.5 Get Upload URLs (Separate step required by Sarvam)
    url_response = _client.post(
        f"{base_url}/upload-files",
        headers=headers,
        json={
            "job_id": job_id,
            "files": [Path(audio_path).name]
        },
        timeout=30.0
    )
    if not url_response.is_success:
        logger.error(f"❌ Sarvam Get Upload URL Error: {url_response.text}")
        url_response.raise_for_status()
    
    upload_data = url_response.json()
    presigned_urls = upload_data.get("upload_urls", {})
    if not presigned_urls:
        logger.error(f"❌ Sarvam Job Error: No upload_urls returned: {upload_data}")
        raise ValueError("Failed to get presigned upload URLs")

    # Get the specific URL for our file
    file_name = Path(audio_path).name
    url_info = presigned_urls.get(file_name, {})
    if not url_info or "file_url" not in url_info:
        url_info = next(iter(presigned_urls.values()), {})
        
    upload_url = url_info.get("file_url")
    if not upload_url:
        raise ValueError(f"Could not find upload_url for {file_name}")

    # 2. Upload File to the provided Presigned URL
    try:
        upload_headers = {
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": "audio/mpeg"
        }
        
        with open(audio_path, "rb") as f:
            upload_response = _client.put(
                upload_url,
                content=f,
                headers=upload_headers,
                timeout=120.0
            )
        
        if upload_response.status_code >= 400:
            logger.error(f"❌ Sarvam Job Upload Error ({upload_response.status_code}): {upload_response.text}")
            upload_response.raise_for_status()
            
    except Exception as e:
        logger.error(f"❌ Upload Exception: {str(e)}")
        raise
    
    logger.info(f"✅ Audio uploaded successfully. Starting job {job_id}...")

    # 3. Start the Job
    start_response = _client.post(f"{base_url}/{job_id}/start", headers=headers)
    if not start_response.is_success:
        logger.error(f"❌ Sarvam Job Start Error: {start_response.text}")
        start_response.raise_for_status()
    logger.info(f"🚀 Sarvam Job {job_id} is now processing...")

    # 4. Poll for results with adaptive backoff
    current_delay = 1.5
    max_retries = 200
    for i in range(max_retries):
        status_response = _client.get(f"{base_url}/{job_id}/status", headers=headers)
        if status_response.is_success:
            status_data = status_response.json()
            status = status_data.get("status") or status_data.get("job_state")
            
            if status and status.lower() == "completed":
                # 5. Get Download URLs for the results
                outputs = status_data.get("job_details", [{}])[0].get("outputs", [])
                if not outputs:
                    raise ValueError("Job completed but no outputs found")
                
                output_file_names = [o.get("file_name") for o in outputs]
                
                download_response = _client.post(
                    f"{base_url}/download-files",
                    headers=headers,
                    json={
                        "job_id": job_id,
                        "files": output_file_names
                    },
                    timeout=30.0
                )
                if not download_response.is_success:
                    raise ValueError(f"Failed to get download URLs: {download_response.text}")
                
                download_data = download_response.json()
                download_urls = download_data.get("download_urls", {})
                
                first_output_name = output_file_names[0]
                json_url = download_urls.get(first_output_name, {}).get("file_url")
                
                if not json_url:
                    raise ValueError(f"No download URL found for {first_output_name}")
                
                result_response = _client.get(json_url, timeout=30.0)
                if result_response.is_success:
                    return _extract_transcript_text(result_response.json())
                else:
                    raise ValueError(f"Failed to download result JSON: {result_response.text}")
            elif status and status.lower() == "failed":
                raise ValueError(f"Sarvam Job failed: {status_data.get('error_message')}")
        
        time.sleep(current_delay)
        # Dynamic backoff multiplier of 1.5, capping at 5.0 seconds
        current_delay = min(5.0, current_delay * 1.5)
        
    raise TimeoutError("Sarvam Batch API timed out after 10 minutes")


def _transcribe_with_openai(audio_path: str, language: str | None = None) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    base_url = (settings.api_base_url or "https://api.openai.com/v1").rstrip("/")
    endpoint = f"{base_url}/audio/transcriptions"

    with open(audio_path, "rb") as audio_file:
        files = {
            "file": (Path(audio_path).name, audio_file, "application/octet-stream"),
        }
        data = {
            "model": settings.openai_transcription_model,
            "temperature": str(settings.whisper_temperature),
            "prompt": settings.asr_prompt,
            "language": language if language else settings.whisper_language,
        }
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data=data,
            files=files,
            timeout=180.0,
        )

    response.raise_for_status()
    payload = response.json()
    return (payload.get("text", "") or "").strip()


def _transcribe_with_whisper(audio_path: str, language: str | None = None) -> str:
    # Prefer faster-whisper (no torch; much smaller install footprint)
    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        segments, _info = model.transcribe(
            audio_path,
            language=language if language else (settings.whisper_language or None),
            beam_size=settings.whisper_beam_size,
            best_of=settings.whisper_best_of,
            temperature=settings.whisper_temperature,
            vad_filter=True,
            initial_prompt=settings.asr_prompt,
        )
        return _join_segments(segments)
    except ImportError:
        pass

    # Fallback to openai-whisper if installed (requires torch)
    try:
        import whisper  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "No Whisper backend installed. Install `faster-whisper` (recommended) "
            "or `openai-whisper`."
        ) from exc

    model = whisper.load_model(settings.whisper_model)
    result = model.transcribe(
        audio_path,
        language=language if language else (settings.whisper_language or None),
        temperature=settings.whisper_temperature,
        initial_prompt=settings.asr_prompt,
    )
    return (result.get("text", "") or "").strip()


def _transcribe_with_assemblyai(audio_path: str, language: str | None = None) -> str:
    try:
        import assemblyai as aai
    except ImportError as exc:
        raise RuntimeError("assemblyai is not installed") from exc

    if not settings.assemblyai_api_key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not set")

    aai.settings.api_key = settings.assemblyai_api_key
    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(
        speech_model=aai.SpeechModel.best,
        language_code=language if language else (settings.whisper_language or "en"),
    )
    transcript = transcriber.transcribe(audio_path, config=config)
    return transcript.text or ""


def _cleanup_medical_transcript(transcript: str) -> str:
    if not transcript.strip() or not settings.enable_medical_transcript_cleanup:
        return transcript.strip()

    logger.info("✨ Starting medical transcript cleanup step...")
    glossary = _parse_glossary(settings.medical_terminology_glossary)
    glossary_text = ", ".join(glossary) if glossary else "No custom glossary provided."

    from app.services.llm_factory import get_utility_llm
    llm = get_utility_llm()
    logger.info(f"🤖 Invoking utility LLM ({llm.__class__.__name__}) for clinical transcript correction...")

    messages = [
        SystemMessage(
            content=(
                "You correct clinical transcripts. Preserve speaker meaning exactly. "
                "Fix likely ASR errors in drug names, anatomy, diagnoses, dosages, frequencies, "
                "routes, and durations. Do not summarize. Do not add facts. Return only the corrected transcript."
            )
        ),
        HumanMessage(
            content=(
                f"Preferred medical terminology: {glossary_text}\n\n"
                f"Transcript:\n{transcript}"
            )
        ),
    ]
    try:
        corrected = llm.invoke(messages)
        content = getattr(corrected, "content", transcript).strip() or transcript.strip()
        logger.info(f"✅ Medical transcript cleanup completed successfully. (Length: {len(content)} chars)")
        return content
    except Exception as e:
        logger.error(f"⚠️ Medical transcript cleanup failed: {e}. Falling back gracefully to raw transcript.")
        return transcript.strip()


def transcribe_audio(audio_path: str, language: str | None = None) -> str:
    provider = settings.asr_provider.lower()
    logger.info(f"🎙️ ASR Provider configured: {provider}")

    # Normalize language for Whisper (2-letter) while keeping full code for Sarvam
    whisper_lang = language
    if whisper_lang and "-" in whisper_lang and len(whisper_lang) > 3:
        whisper_lang = whisper_lang.split("-")[0]

    # Normalize language for Sarvam (needs BCP-47 like en-IN)
    sarvam_lang = language
    if not sarvam_lang or sarvam_lang.lower() == "en" or sarvam_lang.lower() == "unknown":
        sarvam_lang = "en-IN"

    if provider in {"sarvam", "sarvam-ai", "sarvam_ai"}:
        try:
            logger.info(f"🕒 Transcribing with Sarvam primary ASR (language: {sarvam_lang})...")
            transcript = _transcribe_with_sarvam(audio_path, language=sarvam_lang)
            logger.info("✅ Sarvam primary transcription successful.")
        except Exception as e:
            logger.error(f"⚠️ Sarvam transcription failed: {e}. Falling back to local Whisper ASR...")
            transcript = _transcribe_with_whisper(audio_path, language=whisper_lang)
    elif provider == "whisper":
        logger.info("🕒 Transcribing with Whisper...")
        transcript = _transcribe_with_whisper(audio_path, language=whisper_lang)
    elif provider == "openai":
        logger.info("🕒 Transcribing with OpenAI...")
        transcript = _transcribe_with_openai(audio_path, language=language)
    elif provider == "assemblyai":
        logger.info("🕒 Transcribing with AssemblyAI...")
        transcript = _transcribe_with_assemblyai(audio_path, language=language)
    else:
        raise ValueError(f"Unsupported ASR provider: {provider}")

    logger.info("✨ Skipping synchronous transcript cleanup (delegated to parallel cleanup node)...")
    return transcript.strip()
