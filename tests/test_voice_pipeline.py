from core.voice_pipeline import (
    VoicePipeline,
    choose_consensus,
    classify_voice_risk,
    transcript_similarity,
)


class FakeSTT:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def transcribe(self, audio):
        self.calls += 1
        return self.result


class FakeAssistant:
    def __init__(self):
        self.messages = []

    def respond(self, message):
        self.messages.append(message)
        return {
            "answer": f"Svar på: {message}",
            "tools": [],
            "tool_results": {},
        }


class FakeTTS:
    def __init__(self):
        self.spoken = []
        self.stopped = False

    def speak(self, text):
        self.spoken.append(text)

    def stop(self):
        self.stopped = True


def settings(**overrides):
    voice = {
        "enabled": False,
        "tts_enabled": False,
        "redundancy_enabled": True,
        "redundancy_when_confidence_missing": False,
        "primary_confidence_threshold": 0.72,
        "consensus_similarity_threshold": 0.62,
        "redundant_transcript_count": 3,
    }
    voice.update(overrides)
    return {"voice": voice}


def test_similarity_accepts_small_wording_differences():
    score = transcript_similarity(
        "Hur mycket RAM använder datorn?",
        "Hur mycket ram använder min dator?",
    )

    assert score >= 0.62


def test_consensus_uses_two_similar_transcripts_over_one_outlier():
    result = choose_consensus(
        [
            {
                "text": "Hur mycket RAM använder datorn?",
                "confidence": 0.8,
            },
            {
                "text": "Hur mycket ram använder min dator?",
                "confidence": 0.9,
            },
            {
                "text": "Stäng av lampan",
                "confidence": 0.95,
            },
        ]
    )

    assert result["accepted"] is True
    assert result["support"] == 2
    assert "ram" in result["text"].lower()


def test_conflicting_transcripts_require_clarification():
    result = choose_consensus(
        [
            "öppna dörren",
            "stäng av datorn",
            "visa ram status",
        ]
    )

    assert result["accepted"] is False


def test_risk_classifier_flags_destructive_and_hardware_commands():
    assert classify_voice_risk(
        "Radera filen rapport.txt"
    )["level"] == "high"
    assert classify_voice_risk(
        "Styr GPIO17"
    )["level"] == "high"
    assert classify_voice_risk(
        "Hur varmt är det?"
    )["level"] == "low"


def test_high_confidence_low_risk_uses_only_primary():
    assistant = FakeAssistant()
    primary = FakeSTT(
        {
            "text": "Hur mycket RAM används?",
            "confidence": 0.95,
        }
    )
    backup = FakeSTT(
        {
            "text": "backup",
            "confidence": 0.9,
        }
    )
    pipeline = VoicePipeline(
        assistant,
        primary,
        backup_stt=[backup, backup],
        settings=settings(),
    )

    result = pipeline.process_utterance(b"audio")

    assert result["status"] == "completed"
    assert primary.calls == 1
    assert backup.calls == 0
    assert assistant.messages == [
        "Hur mycket RAM används?"
    ]


def test_low_confidence_uses_redundant_stt_and_consensus():
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Hur mycket RAM använder datorn?",
                "confidence": 0.4,
            }
        ),
        backup_stt=[
            FakeSTT(
                {
                    "text": "Hur mycket ram använder min dator?",
                    "confidence": 0.9,
                }
            ),
            FakeSTT(
                {
                    "text": "Hur mycket RAM-minne används?",
                    "confidence": 0.85,
                }
            ),
        ],
        settings=settings(),
    )

    result = pipeline.process_utterance(b"audio")

    assert result["status"] == "completed"
    assert result["consensus"]["support"] >= 2
    assert len(assistant.messages) == 1


def test_high_risk_forces_redundancy_even_with_high_confidence():
    assistant = FakeAssistant()
    backups = [
        FakeSTT(
            {
                "text": "Radera filen rapport.txt",
                "confidence": 0.9,
            }
        ),
        FakeSTT(
            {
                "text": "Radera filen rapport.txt",
                "confidence": 0.9,
            }
        ),
    ]
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Radera filen rapport.txt",
                "confidence": 0.99,
            }
        ),
        backup_stt=backups,
        settings=settings(),
    )

    result = pipeline.process_utterance(b"audio")

    assert result["status"] == "completed"
    assert all(
        provider.calls == 1
        for provider in backups
    )
    assert result["risk"]["level"] == "high"


def test_missing_backup_stt_for_high_risk_requires_clarification():
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Radera filen rapport.txt",
                "confidence": 0.99,
            }
        ),
        backup_stt=[],
        settings=settings(),
    )

    result = pipeline.process_utterance(b"audio")

    assert result["status"] == "clarify"
    assert assistant.messages == []


def test_tts_speaks_answer_when_enabled():
    assistant = FakeAssistant()
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Hej",
                "confidence": 0.99,
            }
        ),
        tts=tts,
        settings=settings(tts_enabled=True),
    )

    result = pipeline.process_utterance(b"audio")

    assert result["status"] == "completed"
    assert tts.spoken == ["Svar på: Hej"]


def test_interrupt_calls_tts_stop():
    tts = FakeTTS()
    pipeline = VoicePipeline(
        FakeAssistant(),
        FakeSTT("Hej"),
        tts=tts,
        settings=settings(),
    )

    assert pipeline.interrupt() is True
    assert tts.stopped is True


class FakeSemanticResolver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def resolve(self, transcripts):
        self.calls.append(list(transcripts))
        return dict(self.result)


def test_semantic_fallback_can_resolve_low_risk_transcripts():
    assistant = FakeAssistant()
    resolver = FakeSemanticResolver(
        {
            "accepted": True,
            "text": "Hur mycket RAM används?",
            "support": 2,
            "confidence": 0.95,
            "reason": "Samma avsikt.",
        }
    )
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Hur mycket minne går åt?",
                "confidence": 0.3,
            }
        ),
        backup_stt=[
            FakeSTT(
                {
                    "text": "Hur mycket RAM används?",
                    "confidence": 0.4,
                }
            ),
            FakeSTT(
                {
                    "text": "Visa minnesbelastningen",
                    "confidence": 0.4,
                }
            ),
        ],
        settings=settings(
            semantic_consensus_enabled=True,
        ),
        semantic_resolver=resolver,
    )

    result = pipeline.process_utterance(b"audio")

    assert result["status"] == "completed"
    assert result["consensus"]["method"] == "semantic"
    assert assistant.messages == [
        "Hur mycket RAM används?"
    ]
    assert len(resolver.calls) == 1


def test_semantic_fallback_is_not_used_for_high_risk_by_default():
    assistant = FakeAssistant()
    resolver = FakeSemanticResolver(
        {
            "accepted": True,
            "text": "Radera filen rapport.txt",
            "support": 2,
            "confidence": 0.99,
        }
    )
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Radera filen rapport.txt",
                "confidence": 0.9,
            }
        ),
        backup_stt=[
            FakeSTT(
                {
                    "text": "Ta bort rapportfilen",
                    "confidence": 0.9,
                }
            ),
            FakeSTT(
                {
                    "text": "Spara rapporten",
                    "confidence": 0.9,
                }
            ),
        ],
        settings=settings(
            semantic_consensus_enabled=True,
            semantic_consensus_for_high_risk=False,
        ),
        semantic_resolver=resolver,
    )

    result = pipeline.process_utterance(b"audio")

    assert result["status"] == "clarify"
    assert resolver.calls == []
    assert assistant.messages == []


def test_semantic_fallback_failure_still_requires_clarification():
    assistant = FakeAssistant()
    resolver = FakeSemanticResolver(
        {
            "accepted": False,
            "reason": "Ingen majoritet.",
        }
    )
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "fråga ett",
                "confidence": 0.2,
            }
        ),
        backup_stt=[
            FakeSTT(
                {
                    "text": "fråga två",
                    "confidence": 0.2,
                }
            ),
            FakeSTT(
                {
                    "text": "fråga tre",
                    "confidence": 0.2,
                }
            ),
        ],
        settings=settings(
            semantic_consensus_enabled=True,
        ),
        semantic_resolver=resolver,
    )

    result = pipeline.process_utterance(b"audio")

    assert result["status"] == "clarify"
    assert len(resolver.calls) == 1
    assert assistant.messages == []
