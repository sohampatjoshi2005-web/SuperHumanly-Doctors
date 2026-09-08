from app.services.transcription_service import transcribe_audio


def asr_tool(audio_path: str) -> str:
    return transcribe_audio(audio_path)
