
import os
import sys
from pathlib import Path

# Add the project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

from app.services.transcription_service import transcribe_audio
from app.core.config import settings

def test_transcription():
    audio_path = "Audio Recording Whisper.mp3"
    if not os.path.exists(audio_path):
        print(f"❌ Audio file {audio_path} not found!")
        return

    print(f"🎙️ Testing transcription for: {audio_path}")
    print(f"📡 Provider: {settings.asr_provider}")
    
    try:
        transcript = transcribe_audio(audio_path, language="en-IN")
        print("\n✅ Transcription Success!")
        print(f"📝 Transcript: {transcript}")
    except Exception as e:
        print(f"\n❌ Transcription Failed: {str(e)}")

if __name__ == "__main__":
    test_transcription()
