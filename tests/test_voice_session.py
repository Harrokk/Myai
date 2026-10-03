from modules.voice.session import VoiceSession


class FakeSTT:
    def __init__(self, result, name="fake-stt"):
        self.result = result
        self.name = name
        self.calls = 0

    def transcribe(self, audio):
        self.calls += 1
        return dict(self.result)


class FakeAssistant:
    def __init__(self):
        self.messages = []

    def respond(self, text):
        self.messages.append(text)
        return {
            "answer": f"Svar på: {text}",
            "tools": [],
            "tool_results": {},
        }


class FakeTTS:
    def __init__(self, fail=False):
        self.fail = fail
        self.spoken = []
        self.stop_calls = 0

    def speak(self, text):
        if self.fail:
            raise RuntimeError("TTS-fel")
        self.spoken.append(text)

    def stop(self):
        self.stop_calls += 1


def settings(enabled=True):
    return {
        "voice": {
            "enabled": enabled,
            "speak_responses": True,
            "primary_confidence_threshold": 0.80,
            "consensus_confidence_threshold": 0.75,
            "high_risk_confidence_threshold": 0.90,
            "agreement_threshold": 0.72,
            "uncertain_word_limit": 1,
            "max_interpretations": 3,
            "redundant_for_high_risk": True,
        }
    }


def transcript(text, confidence=0.95):
    return {
        "text": text,
        "confidence": confidence,
        "uncertain_words": 0,
    }


def test_disabled_voice_does_not_call_stt():
    stt = FakeSTT(transcript("hej"))
    session = VoiceSession(
        FakeAssistant(),
        [stt],
        settings=settings(enabled=False),
    )

    result = session.handle_audio(b"audio")

    assert result["status"] == "disabled"
    assert stt.calls == 0


def test_low_risk_high_confidence_uses_only_primary_stt():
    primary = FakeSTT(
        transcript(
            "Hur mycket RAM använder datorn?",
            0.96,
        )
    )
    alternate = FakeSTT(
        transcript(
            "Hur mycket ram använder min dator?",
            0.95,
        )
    )
    assistant = FakeAssistant()
    tts = FakeTTS()
    session = VoiceSession(
        assistant,
        [primary, alternate],
        tts,
        settings(),
    )

    result = session.handle_audio(b"audio")

    assert result["status"] == "completed"
    assert primary.calls == 1
    assert alternate.calls == 0
    assert assistant.messages == [
        "Hur mycket RAM använder datorn?"
    ]
    assert result["spoken"] is True
    assert len(tts.spoken) == 1


def test_high_risk_command_requests_second_stt():
    primary = FakeSTT(
        transcript(
            "Radera filen rapport.txt",
            0.98,
        ),
        name="primary",
    )
    second = FakeSTT(
        transcript(
            "Radera rapport.txt",
            0.97,
        ),
        name="second",
    )
    assistant = FakeAssistant()
    session = VoiceSession(
        assistant,
        [primary, second],
        settings=settings(),
    )

    result = session.handle_audio(b"audio")

    assert result["status"] == "completed"
    assert primary.calls == 1
    assert second.calls == 1
    assert result["decision"]["risk"] == "high"
    assert result["decision"]["agreement_count"] == 2


def test_conflicting_risky_transcripts_do_not_reach_assistant():
    engines = [
        FakeSTT(
            transcript(
                "Radera filen rapport.txt",
                0.98,
            )
        ),
        FakeSTT(
            transcript(
                "Läs filen rapport.txt",
                0.98,
            )
        ),
        FakeSTT(
            transcript(
                "Skapa filen rapport.txt",
                0.98,
            )
        ),
    ]
    assistant = FakeAssistant()
    session = VoiceSession(
        assistant,
        engines,
        settings=settings(),
    )

    result = session.handle_audio(b"audio")

    assert result["status"] == "clarify"
    assert assistant.messages == []


def test_low_confidence_primary_can_be_resolved_by_second_stt():
    engines = [
        FakeSTT(
            transcript(
                "Visa systemstatus",
                0.60,
            )
        ),
        FakeSTT(
            transcript(
                "Visa system status",
                0.94,
            )
        ),
    ]
    assistant = FakeAssistant()
    session = VoiceSession(
        assistant,
        engines,
        settings=settings(),
    )

    result = session.handle_audio(b"audio")

    assert result["status"] == "completed"
    assert len(result["transcripts"]) == 2
    assert assistant.messages


def test_tts_failure_does_not_erase_assistant_answer():
    assistant = FakeAssistant()
    tts = FakeTTS(fail=True)
    session = VoiceSession(
        assistant,
        [
            FakeSTT(
                transcript("Visa status", 0.95)
            )
        ],
        tts,
        settings(),
    )

    result = session.handle_audio(b"audio")

    assert result["status"] == "completed"
    assert result["assistant_result"]["answer"]
    assert result["spoken"] is False
    assert result["tts_error"] == "TTS-fel"


def test_interrupt_stops_tts():
    tts = FakeTTS()
    session = VoiceSession(
        FakeAssistant(),
        [],
        tts,
        settings(),
    )

    result = session.interrupt()

    assert result["stopped"] is True
    assert tts.stop_calls == 1


def test_interrupt_reports_unsupported_tts():
    class SpeakOnly:
        def speak(self, text):
            pass

    session = VoiceSession(
        FakeAssistant(),
        [],
        SpeakOnly(),
        settings(),
    )

    result = session.interrupt()

    assert result["stopped"] is False
    assert "stöder inte" in result["reason"]
