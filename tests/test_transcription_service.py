from app.services import transcription_service


def test_transcribe_audio_falls_back_to_whisper(monkeypatch):
    monkeypatch.setattr(transcription_service.settings, "asr_provider", "sarvam")
    monkeypatch.setattr(transcription_service.settings, "sarvam_api_key", "test-key")

    def fail_sarvam(_audio_path: str, language: str | None = None) -> str:
        raise RuntimeError("sarvam unavailable")

    monkeypatch.setattr(transcription_service, "_transcribe_with_sarvam", fail_sarvam)
    monkeypatch.setattr(transcription_service, "_transcribe_with_whisper", lambda _audio_path, language=None: "whisper fallback")
    monkeypatch.setattr(transcription_service, "_cleanup_medical_transcript", lambda transcript: transcript)

    assert transcription_service.transcribe_audio("/tmp/sample.wav") == "whisper fallback"


def test_transcribe_audio_uses_sarvam_first(monkeypatch):
    monkeypatch.setattr(transcription_service.settings, "asr_provider", "sarvam")
    monkeypatch.setattr(transcription_service.settings, "sarvam_api_key", "test-key")

    monkeypatch.setattr(transcription_service, "_transcribe_with_sarvam", lambda _audio_path, language=None: "sarvam primary")

    def fail_whisper(_audio_path: str, language: str | None = None) -> str:
        raise AssertionError("whisper fallback should not be used when Sarvam succeeds")

    monkeypatch.setattr(transcription_service, "_transcribe_with_whisper", fail_whisper)
    monkeypatch.setattr(transcription_service, "_cleanup_medical_transcript", lambda transcript: transcript)

    assert transcription_service.transcribe_audio("/tmp/sample.wav") == "sarvam primary"