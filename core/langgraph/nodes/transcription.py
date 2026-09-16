from typing import Dict, Any
from app.core.langgraph.tools.asr import asr_tool


import asyncio

async def transcription_node(state: Dict[str, Any]) -> Dict[str, Any]:
    # If transcript is already provided (Text Input), don't return it again 
    # as it causes a conflict in LangGraph v0.1+
    if state.get("transcript"):
        return {}
        
    audio_path = state.get("audio_path")
    language = state.get("language")
    if not audio_path:
        raise ValueError("audio_path is required when transcript is missing")

    # Transcription is CPU/IO heavy, run in threadpool to avoid blocking event loop
    from app.services.transcription_service import transcribe_audio
    transcript = await asyncio.to_thread(transcribe_audio, audio_path, language=language)
    return {"transcript": transcript}
