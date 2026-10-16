"""Full synthetic VoiceSession path, never hardware, native provider or LLM.

Tests do NOT enable the stored OFF profile: in-memory flags are changed only
to exercise the real VoiceSession/VoicePipeline using wholly fake providers.
No sounddevice, pyttsx3, faster_whisper, GenieX, model, or network is called.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.voice_session import VoiceSession
from core.runtime_safety_attestation import summarize
from scripts.ventuno_isolated_voice_stage_contract import SOURCE, candidate


class FakeMicrophone:
    def __init__(self, frames):
        self.frames = list(frames)
        self.running = False
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1
        self.running = True
        return True

    def stop(self):
        self.stops += 1
        self.running = False
        return True

    def read_frame(self):
        if not self.running:
            raise AssertionError("read after synthetic microphone was stopped")
        if not self.frames:
            raise AssertionError("synthetic test attempted unbounded capture")
        return {"frame": self.frames.pop(0), "overflowed": False}


class FakeVAD:
    def __init__(self):
        self.decisions = iter([True, False, False])

    def is_speech(self, _frame):
        return next(self.decisions, False)


class FakeSTT:
    def __init__(self, transcript="Vad är klockan?"):
        self.transcript = transcript
        self.frames = []
        self.releases = 0

    def transcribe(self, audio):
        self.frames.append(bytes(audio))
        return {"text": self.transcript, "language": "sv", "confidence": 0.99}

    def release_for_inference(self):
        self.releases += 1
        return True


class FakeAssistant:
    def __init__(self):
        self.queries = []
        self.llm = None

    def respond(self, text):
        self.queries.append(text)
        return {
            "answer": "Det här är ett syntetiskt testsvar.",
            "tools": [],
            "tool_results": {},
        }


class FakeTTS:
    def __init__(self):
        self.spoken = []
        self.stops = 0

    def speak(self, text):
        self.spoken.append(text)

    def stop(self):
        self.stops += 1
        return True


def _session(transcript="Vad är klockan?"):
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    config = candidate(source)
    # These ephemeral in-memory overrides only activate FULLY FAKE
    # providers; never write them to the disabled source JSON file.
    voice = config["voice"]
    voice.update({
        "enabled": True,
        "tts_enabled": True,
        "handsfree_enabled": False,
        "release_microphone_during_inference": True,
        "release_stt_before_model": True,
        "model_handoff_delay_seconds": 0,
        "vad_start_speech_frames": 1,
        "vad_end_silence_frames": 2,
        "vad_max_frames": 30,
        "session_max_wait_frames": 10,
    })
    mic = FakeMicrophone([b"AA", b"BB", b"CC"])
    stt = FakeSTT(transcript)
    assistant = FakeAssistant()
    tts = FakeTTS()
    session = VoiceSession(
        assistant,
        settings=config,
        components={
            "enabled": True,
            "microphone": mic,
            "vad": FakeVAD(),
            "primary_stt": stt,
            "backup_stt": [],
            "tts": tts,
        },
        sleep_fn=lambda _: None,
    )
    return session, mic, stt, assistant, tts, config


def test_complete_synthetic_pcm_stt_llm_tts_and_stop(tmp_path):
    session, mic, stt, assistant, tts, config = _session()
    before = sorted(tmp_path.rglob("*"))
    result = session.run_once(max_wait_frames=6)
    assert result["status"] == "utterance_complete"
    assert result["voice_result"]["status"] == "completed"
    assert stt.frames == [b"AABBCC"]
    assert assistant.queries == ["Vad är klockan?"]
    assert tts.spoken == ["Det här är ett syntetiskt testsvar."]
    assert stt.releases == 1
    assert mic.starts == 2  # resume after inference
    assert mic.stops == 1
    assert session.stop() is True
    assert mic.stops == 2
    assert tts.stops >= 1
    assert mic.running is False
    assert session.running is False
    assert sorted(tmp_path.rglob("*")) == before
    assert config["memory"]["auto_save_enabled"] is False
    assert config["memory"]["database"] == "runtime/isolated_voice_trial/memory.db"
    assert summarize(config)["voice_and_writes_off"] is False  # fake voice was enabled
    assert json.loads(SOURCE.read_text(encoding="utf-8"))["voice"]["enabled"] is False


def test_high_risk_synthetic_instruction_not_dispatched_or_spoken_as_completed():
    session, mic, stt, assistant, tts, _ = _session("Radera minnet")
    result = session.run_once(max_wait_frames=6)
    assert result["status"] == "utterance_complete"
    assert result["voice_result"]["status"] != "completed"
    assert assistant.queries == []
    session.stop()
    assert mic.running is False


def test_synthetic_stt_error_fails_closed_and_does_not_call_llm():
    session, mic, stt, assistant, tts, _ = _session()
    def fail(_pcm):
        raise RuntimeError("PRIVATE_PCM_SENSITIVE_TEST_MUST_NOT_LEAK")
    stt.transcribe = fail
    result = session.run_once(max_wait_frames=6)
    assert result["status"] == "utterance_complete"
    assert result["voice_result"]["status"] == "clarify"
    assert "PRIVATE_PCM" not in json.dumps(result)
    assert assistant.queries == []
    session.stop()
    assert mic.running is False
