from core.voice_pipeline import (
    VoicePipeline,
    choose_consensus,
    classify_voice_risk,
    transcript_similarity,
    tts_echo_similarity,
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


class ToolPlanningAssistant(FakeAssistant):
    def __init__(self, tool_name):
        super().__init__()
        self.tool_name = tool_name
        self.tools = {
            tool_name: {
                "description": "test tool",
                "safety": {
                    "effect": "write",
                    "voice_confirmation_required": True,
                },
            }
        }

    def preview_tool_plan(self, message):
        return {
            "steps": [
                {
                    "tool": self.tool_name,
                    "input": message,
                }
            ]
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
            "text": "RAM-status tack",
            "support": 2,
            "confidence": 0.95,
            "reason": "Samma avsikt.",
        }
    )
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Visa arbetsminnets belastning",
                "confidence": 0.3,
            }
        ),
        backup_stt=[
            FakeSTT(
                {
                    "text": "RAM-status tack",
                    "confidence": 0.4,
                }
            ),
            FakeSTT(
                {
                    "text": "Kontrollera mängden använt minne",
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
        "RAM-status tack"
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
                    "text": "Starta om datorn",
                    "confidence": 0.9,
                }
            ),
            FakeSTT(
                {
                    "text": "Visa nätverksstatus",
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
                    "text": "processorns temperatur",
                    "confidence": 0.2,
                }
            ),
            FakeSTT(
                {
                    "text": "lista usb enheter",
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



class FakeClock:
    def __init__(self, value=100.0):
        self.value = float(value)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


def test_tts_echo_similarity_detects_partial_spoken_text():
    score = tts_echo_similarity(
        "hur mycket ram används just nu",
        "Svar på hur mycket ram används just nu i datorn",
        min_words=3,
    )

    assert score >= 0.78


def test_tts_echo_similarity_ignores_very_short_phrases():
    assert tts_echo_similarity(
        "ja tack",
        "ja tack det gör vi",
        min_words=3,
    ) == 0.0


def test_recent_tts_echo_is_ignored_before_assistant_call():
    assistant = FakeAssistant()
    stt = FakeSTT(
        {
            "text": "Hur mycket RAM används?",
            "confidence": 0.99,
        }
    )
    tts = FakeTTS()
    clock = FakeClock()
    pipeline = VoicePipeline(
        assistant,
        stt,
        tts=tts,
        settings=settings(
            tts_enabled=True,
            echo_guard_enabled=True,
            echo_guard_window_seconds=5.0,
            echo_guard_similarity_threshold=0.78,
            echo_guard_min_words=3,
        ),
        clock=clock,
    )

    first = pipeline.process_utterance(
        b"first"
    )
    assert first["status"] == "completed"
    assert len(assistant.messages) == 1

    stt.result = {
        "text": "Svar på hur mycket RAM används",
        "confidence": 0.99,
    }
    second = pipeline.process_utterance(
        b"echo"
    )

    assert second["status"] == "ignored_echo"
    assert second["echo_similarity"] >= 0.78
    assert len(assistant.messages) == 1


def test_echo_guard_expires_after_configured_window():
    assistant = FakeAssistant()
    stt = FakeSTT(
        {
            "text": "Hur mycket RAM används?",
            "confidence": 0.99,
        }
    )
    clock = FakeClock()
    pipeline = VoicePipeline(
        assistant,
        stt,
        tts=FakeTTS(),
        settings=settings(
            tts_enabled=True,
            echo_guard_enabled=True,
            echo_guard_window_seconds=2.0,
        ),
        clock=clock,
    )

    pipeline.process_utterance(b"first")
    clock.advance(3.0)
    stt.result = {
        "text": "Svar på hur mycket RAM används",
        "confidence": 0.99,
    }

    result = pipeline.process_utterance(
        b"later"
    )

    assert result["status"] == "completed"
    assert len(assistant.messages) == 2


def test_high_risk_transcript_is_not_silently_echo_suppressed_by_default():
    assistant = FakeAssistant()
    primary = FakeSTT(
        {
            "text": "Radera filen rapport txt nu",
            "confidence": 0.99,
        }
    )
    backups = [
        FakeSTT(
            {
                "text": "Radera filen rapport txt nu",
                "confidence": 0.95,
            }
        ),
        FakeSTT(
            {
                "text": "Radera filen rapport txt nu",
                "confidence": 0.95,
            }
        ),
    ]
    clock = FakeClock()
    pipeline = VoicePipeline(
        assistant,
        primary,
        backup_stt=backups,
        settings=settings(
            echo_guard_enabled=True,
            echo_guard_for_high_risk=False,
        ),
        clock=clock,
    )
    pipeline.last_tts_text = (
        "Radera filen rapport txt nu"
    )
    pipeline.last_tts_started_at = clock()

    result = pipeline.process_utterance(
        b"audio"
    )

    assert result["status"] == "completed"
    assert result["risk"]["level"] == "high"
    assert len(assistant.messages) == 1



def high_risk_pipeline(
    clock=None,
    tts=None,
    confirmation_confidence=0.95,
):
    assistant = FakeAssistant()
    primary = FakeSTT(
        {
            "text": "Radera filen rapport txt",
            "confidence": 0.99,
        }
    )
    backups = [
        FakeSTT(
            {
                "text": "Radera filen rapport txt",
                "confidence": 0.95,
            }
        ),
        FakeSTT(
            {
                "text": "Radera filen rapport txt",
                "confidence": 0.95,
            }
        ),
    ]
    pipeline = VoicePipeline(
        assistant,
        primary,
        backup_stt=backups,
        tts=tts,
        settings=settings(
            tts_enabled=tts is not None,
            high_risk_confirmation_enabled=True,
            high_risk_confirmation_window_seconds=15,
            high_risk_confirmation_min_confidence=0.80,
        ),
        clock=clock,
    )
    return pipeline, assistant, primary, confirmation_confidence


def test_high_risk_command_waits_for_explicit_confirmation():
    clock = FakeClock()
    pipeline, assistant, primary, _ = high_risk_pipeline(
        clock=clock
    )

    first = pipeline.process_utterance(
        b"danger"
    )

    assert first["status"] == "confirmation_required"
    assert assistant.messages == []
    assert pipeline.pending_confirmation is not None

    primary.result = {
        "text": "bekräfta",
        "confidence": 0.95,
    }
    # Approval must come from separate STT instances even at 0.95.
    for backup in pipeline.backup_stt:
        backup.result = {"text": "bekräfta", "confidence": 0.95}
    second = pipeline.process_utterance(
        b"confirm"
    )

    assert second["status"] == "completed"
    assert assistant.messages == [
        "Radera filen rapport txt"
    ]
    assert second["confirmation"]["confirmed"] is True
    assert pipeline.pending_confirmation is None


def test_plain_yes_does_not_confirm_high_risk_command():
    pipeline, assistant, primary, _ = high_risk_pipeline(
        clock=FakeClock()
    )
    pipeline.process_utterance(b"danger")

    primary.result = {
        "text": "ja",
        "confidence": 0.99,
    }
    result = pipeline.process_utterance(
        b"yes"
    )

    assert result["status"] == "confirmation_required"
    assert assistant.messages == []
    assert pipeline.pending_confirmation is not None


def test_cancel_clears_pending_high_risk_command():
    pipeline, assistant, primary, _ = high_risk_pipeline(
        clock=FakeClock()
    )
    pipeline.process_utterance(b"danger")

    primary.result = {
        "text": "avbryt",
        "confidence": 0.99,
    }
    result = pipeline.process_utterance(
        b"cancel"
    )

    assert result["status"] == "confirmation_cancelled"
    assert assistant.messages == []
    assert pipeline.pending_confirmation is None


def test_low_confidence_confirmation_does_not_execute():
    pipeline, assistant, primary, _ = high_risk_pipeline(
        clock=FakeClock()
    )
    pipeline.process_utterance(b"danger")

    primary.result = {
        "text": "bekräfta",
        "confidence": 0.50,
    }
    result = pipeline.process_utterance(
        b"confirm"
    )

    assert result["status"] == "confirmation_required"
    assert assistant.messages == []
    assert pipeline.pending_confirmation is not None


def test_pending_confirmation_expires():
    clock = FakeClock()
    pipeline, assistant, primary, _ = high_risk_pipeline(
        clock=clock
    )
    pipeline.process_utterance(b"danger")
    clock.advance(16)

    primary.result = {
        "text": "bekräfta",
        "confidence": 0.99,
    }
    result = pipeline.process_utterance(
        b"late"
    )

    assert result["status"] == "confirmation_expired"
    assert assistant.messages == []
    assert pipeline.pending_confirmation is None


def test_confirmation_prompt_can_be_spoken_without_executing_command():
    tts = FakeTTS()
    pipeline, assistant, _, _ = high_risk_pipeline(
        clock=FakeClock(),
        tts=tts,
    )

    result = pipeline.process_utterance(
        b"danger"
    )

    assert result["status"] == "confirmation_required"
    assert assistant.messages == []
    assert len(tts.spoken) == 1
    assert "bekräfta" in tts.spoken[0].lower()



def test_missing_confirmation_confidence_can_use_redundant_stt_majority():
    pipeline, assistant, primary, _ = high_risk_pipeline(
        clock=FakeClock()
    )
    pipeline.process_utterance(b"danger")

    primary.result = {
        "text": "bekräfta",
        "confidence": None,
    }
    pipeline.backup_stt[0].result = {
        "text": "bekräfta",
        "confidence": None,
    }
    pipeline.backup_stt[1].result = {
        "text": "bekräfta",
        "confidence": None,
    }

    result = pipeline.process_utterance(
        b"confirm"
    )

    assert result["status"] == "completed"
    assert result["confirmation"]["confirmed"] is True
    assert result["confirmation"]["support"] == 3
    assert assistant.messages == [
        "Radera filen rapport txt"
    ]


def test_missing_confirmation_confidence_without_majority_does_not_execute():
    pipeline, assistant, primary, _ = high_risk_pipeline(
        clock=FakeClock()
    )
    pipeline.process_utterance(b"danger")

    primary.result = {
        "text": "bekräfta",
        "confidence": None,
    }
    pipeline.backup_stt[0].result = {
        "text": "något annat",
        "confidence": None,
    }
    pipeline.backup_stt[1].result = {
        "text": "avbryt",
        "confidence": None,
    }

    result = pipeline.process_utterance(
        b"confirm"
    )

    # One explicit cancellation vetoes even the other confirmation.
    assert result["status"] == "confirmation_cancelled"
    assert assistant.messages == []
    assert pipeline.pending_confirmation is None


class FakeStreamingAssistant:
    def __init__(self):
        self.messages = []

    def respond(self, message):
        raise AssertionError(
            "respond() ska inte användas när streaming är aktiverad."
        )

    def respond_stream(
        self,
        message,
        on_chunk=None,
    ):
        self.messages.append(message)
        chunks = [
            "Första meningen. ",
            "Andra meningen.",
        ]

        for chunk in chunks:
            if on_chunk is not None:
                on_chunk(chunk)

        return {
            "answer": "".join(chunks),
            "tools": [],
            "tool_results": {},
            "streamed": True,
        }


def test_voice_pipeline_can_stream_llm_into_tts_queue():
    assistant = FakeStreamingAssistant()
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Berätta något",
                "confidence": 0.99,
            }
        ),
        tts=tts,
        settings=settings(
            tts_enabled=True,
            llm_streaming_enabled=True,
            stream_tts_min_chars=5,
            stream_tts_max_chars=100,
        ),
    )

    result = pipeline.process_utterance(
        b"audio"
    )

    assert result["status"] == "completed"
    assert result["assistant"]["streamed"] is True
    assert pipeline.streaming_tts is not None
    assert pipeline.streaming_tts.wait(
        timeout=1
    ) is True
    assert tts.spoken == [
        "Första meningen.",
        "Andra meningen.",
    ]
    assert assistant.messages == [
        "Berätta något"
    ]


def test_voice_interrupt_stops_streaming_tts_queue():
    assistant = FakeStreamingAssistant()
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant,
        FakeSTT(
            {
                "text": "Berätta något",
                "confidence": 0.99,
            }
        ),
        tts=tts,
        settings=settings(
            tts_enabled=True,
            llm_streaming_enabled=True,
            stream_tts_min_chars=5,
        ),
    )

    pipeline.process_utterance(
        b"audio"
    )
    pipeline.interrupt()

    assert tts.stopped is True



def test_resource_handoff_hook_runs_after_stt_before_assistant():
    events = []

    class OrderedSTT:
        def transcribe(self, audio):
            events.append("stt")
            return {
                "text": "Hej",
                "confidence": 0.99,
            }

    class OrderedAssistant:
        def respond(self, message):
            events.append("assistant")
            return {
                "answer": "Svar",
                "tools": [],
                "tool_results": {},
            }

    pipeline = VoicePipeline(
        OrderedAssistant(),
        OrderedSTT(),
        settings=settings(),
        before_assistant=lambda: events.append(
            "handoff"
        ),
    )

    result = pipeline.process_utterance(
        b"audio"
    )

    assert result["status"] == "completed"
    assert events == [
        "stt",
        "handoff",
        "assistant",
    ]


def test_selected_write_tool_requires_confirmation_even_without_risk_words():
    assistant = ToolPlanningAssistant(
        "workspace_write"
    )
    primary = FakeSTT(
        {
            "text": "Skapa filen notes txt med innehållet hej",
            "confidence": 0.99,
        }
    )
    backups = [
        FakeSTT(
            {
                "text": "Skapa filen notes txt med innehållet hej",
                "confidence": 0.98,
            }
        ),
        FakeSTT(
            {
                "text": "Skapa filen notes txt med innehållet hej",
                "confidence": 0.97,
            }
        ),
    ]
    pipeline = VoicePipeline(
        assistant,
        primary,
        backup_stt=backups,
        settings=settings(
            high_risk_confirmation_enabled=True,
        ),
        clock=FakeClock(),
    )

    first = pipeline.process_utterance(
        b"write"
    )

    assert first["status"] == "confirmation_required"
    assert first["risk"]["level"] == "high"
    assert first["risk"]["tool_names"] == [
        "workspace_write"
    ]
    assert assistant.messages == []

    primary.result = {
        "text": "bekräfta",
        "confidence": 0.99,
    }
    for backup in pipeline.backup_stt:
        backup.result = {"text": "bekräfta", "confidence": 0.95}
    second = pipeline.process_utterance(
        b"confirm"
    )

    assert second["status"] == "completed"
    assert assistant.messages == [
        "Skapa filen notes txt med innehållet hej"
    ]


def test_high_risk_negation_disagreement_blocks_stt_consensus():
    cases = (
        ["Radera filen rapport.txt",
         "Radera inte filen rapport.txt",
         "Radera inte filen rapport.txt"],
        ["Radera inte filen rapport.txt",
         "Radera filen rapport.txt",
         "Radera filen rapport.txt"],
        ["Do not delete the file",
         "Delete the file",
         "Delete the file"],
    )
    for utterances in cases:
        result = choose_consensus([
            {"text": text, "confidence": 0.99}
            for text in utterances
        ])
        assert result["accepted"] is False
        assert result["text"] is None
        assert result["support"] == 0


def test_high_risk_negation_mismatch_never_calls_assistant():
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant,
        FakeSTT({"text": "Radera filen rapport.txt", "confidence": 0.99}),
        backup_stt=[
            FakeSTT({"text": "Radera inte filen rapport.txt", "confidence": 0.99}),
            FakeSTT({"text": "Radera inte filen rapport.txt", "confidence": 0.99}),
        ],
        settings=settings(),
    )
    result = pipeline.process_utterance(b"synthetic-fake-audio")
    assert result["status"] == "clarify"
    assert assistant.messages == []


def test_unanimous_nonnegated_high_risk_still_reaches_existing_confirmation_logic():
    result = choose_consensus([
        "Radera filen rapport.txt",
        "Radera filen rapport.txt",
        "Radera filen rapport.txt",
    ])
    assert result["accepted"] is True
    assert result["support"] == 3


def test_malformed_or_nonfinite_stt_confidence_never_becomes_high():
    from core.voice_pipeline import normalize_stt_result
    for bad in (float("nan"), float("inf"), float("-inf"), "invalid", True, {}, []):
        normalized = normalize_stt_result({"text": "bekräfta", "confidence": bad})
        assert normalized["confidence"] is None, repr(bad)
    assert normalize_stt_result({"text": "ok", "confidence": "0.95"})["confidence"] == 0.95



def test_highrisk_similar_but_different_delete_targets_do_not_vote():
    # All three share most words; ordinary fuzzy Jaccard would agree.
    r = choose_consensus([
        {"text": "Radera filen rapport ett", "confidence": 0.98},
        {"text": "Radera filen rapport två", "confidence": 0.99},
        {"text": "Radera filen rapport tre", "confidence": 0.97},
    ])
    assert r["accepted"] is False
    assert r["text"] is None
    assert "Högriskkommandot" in r["reason"]


def test_highrisk_two_matching_targets_over_differing_outlier():
    r = choose_consensus([
        {"text": "Radera filen rapport ett", "confidence": 0.75},
        {"text": "Radera filen rapport två", "confidence": 0.99},
        {"text": "radera filen rapport ETT!", "confidence": 0.85},
    ])
    assert r["accepted"] is True
    assert r["support"] == 2
    assert "ett" in r["text"].lower()


def test_highrisk_similar_phrasings_are_not_equivalent_authorization():
    r = choose_consensus([
        "Stäng av datorn nu",
        "Stäng av datorn genast",
        "Stäng av datorn omedelbart",
    ])
    assert r["accepted"] is False
    assert r["support"] == 1


def test_lowrisk_fuzzy_transcript_consensus_remains_unchanged():
    r = choose_consensus([
        "Hur mycket RAM använder datorn?",
        "Hur mycket ram använder min dator?",
        "Hitta närmaste postlåda",
    ])
    assert r["accepted"] is True
    assert r["support"] == 2


def test_highrisk_disagreeing_targets_require_clarification_without_tool_call():
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant,
        FakeSTT({"text": "Radera filen rapport ett", "confidence": 0.99}),
        backup_stt=[
            FakeSTT({"text": "Radera filen rapport två", "confidence": 0.99}),
            FakeSTT({"text": "Radera filen rapport tre", "confidence": 0.99}),
        ],
        settings=settings(),
    )
    result = pipeline.process_utterance(b"synthetic-audio")
    assert result["status"] == "clarify"
    assert assistant.messages == []
    assert result["consensus"]["accepted"] is False


def test_same_stt_instance_repeated_cannot_fake_highrisk_majority():
    assistant = FakeAssistant()
    primary = FakeSTT({"text": "Radera filen test", "confidence": 0.99})
    duplicate = FakeSTT({"text": "Radera filen test", "confidence": 0.99})
    pipeline = VoicePipeline(
        assistant, primary,
        backup_stt=[duplicate, duplicate],
        settings=settings(),
    )
    result = pipeline.process_utterance(b"synthetic-audio")
    assert result["status"] == "clarify"
    assert primary.calls == 1
    assert duplicate.calls == 1
    assert assistant.messages == []


def test_primary_stt_reused_as_backup_not_independent():
    assistant = FakeAssistant()
    primary = FakeSTT({"text": "Radera filen test", "confidence": 0.99})
    independent = FakeSTT({"text": "Radera filen test", "confidence": 0.90})
    pipeline = VoicePipeline(
        assistant, primary,
        backup_stt=[primary, independent],
        settings=settings(),
    )
    result = pipeline.process_utterance(b"synthetic-audio")
    assert result["status"] == "clarify"
    assert primary.calls == 1
    assert independent.calls == 1
    assert assistant.messages == []


def test_duplicate_backup_cannot_fake_weak_confirmation_majority():
    clock = FakeClock()
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=clock)
    first = pipeline.process_utterance(b"danger")
    assert first["status"] == "confirmation_required"
    duplicate = FakeSTT({"text": "bekräfta", "confidence": None})
    pipeline.backup_stt = [duplicate, duplicate]
    primary.result = {"text": "bekräfta", "confidence": None}
    result = pipeline.process_utterance(b"confirm")
    assert result["status"] == "confirmation_required"
    assert result["confirmation_confidence"] is None
    assert duplicate.calls == 1
    assert assistant.messages == []


def test_two_different_backup_instances_can_confirm_without_confidence():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    first = pipeline.process_utterance(b"danger")
    assert first["status"] == "confirmation_required"
    primary.result = {"text": "bekräfta", "confidence": None}
    for backup in pipeline.backup_stt:
        backup.result = {"text": "bekräfta", "confidence": None}
    result = pipeline.process_utterance(b"confirm")
    assert result["status"] == "completed"
    assert result["confirmation"]["confirmed"] is True
    assert len(assistant.messages) == 1



def test_highrisk_single_transcript_never_claims_consensus():
    result = choose_consensus(["Radera filen rapport.txt"])
    assert result["accepted"] is False
    assert result["support"] == 1
    assert result["text"] is None
    assert choose_consensus(["Hur mycket RAM används?"])["accepted"] is True


def test_highrisk_stt_redundancy_cannot_be_disabled_in_settings():
    assistant = FakeAssistant()
    a = FakeSTT({"text": "Radera filen ett", "confidence": 0.99})
    b = FakeSTT({"text": "Radera filen ett", "confidence": 0.98})
    c = FakeSTT({"text": "Radera filen ett", "confidence": 0.97})
    pipeline = VoicePipeline(
        assistant, a, backup_stt=[b, c],
        settings=settings(redundancy_enabled=False),
    )
    result = pipeline.process_utterance(b"synthetic-audio")
    assert result["status"] == "completed"
    assert len(result["consensus"]["transcripts"]) == 3
    assert b.calls == c.calls == 1
    assert len(assistant.messages) == 1


def test_highrisk_three_independent_votes_required_even_if_config_says_two():
    assistant = FakeAssistant()
    a = FakeSTT({"text": "Radera filen ett", "confidence": 0.99})
    b = FakeSTT({"text": "Radera filen ett", "confidence": 0.99})
    pipeline = VoicePipeline(
        assistant, a, backup_stt=[b],
        settings=settings(redundant_transcript_count=2),
    )
    result = pipeline.process_utterance(b"synthetic-audio")
    assert result["status"] == "clarify"
    assert b.calls == 1
    assert assistant.messages == []


def test_highrisk_semantic_switch_cannot_overrule_nonmatching_targets():
    assistant = FakeAssistant()
    semantic = FakeSemanticResolver({
        "accepted": True,
        "text": "Radera filen rapport ett",
        "support": 3,
        "confidence": 1.0,
    })
    pipeline = VoicePipeline(
        assistant,
        FakeSTT({"text": "Radera filen rapport ett", "confidence": 0.99}),
        backup_stt=[
            FakeSTT({"text": "Radera filen rapport två", "confidence": 0.99}),
            FakeSTT({"text": "Radera filen rapport tre", "confidence": 0.99}),
        ],
        settings=settings(
            semantic_consensus_enabled=True,
            semantic_consensus_for_high_risk=True,
        ),
        semantic_resolver=semantic,
    )
    result = pipeline.process_utterance(b"synthetic-audio")
    assert result["status"] == "clarify"
    assert semantic.calls == []
    assert assistant.messages == []



def test_safe_majority_remains_possible_with_unrelated_dangerous_outlier():
    r = choose_consensus([
        {"text": "Hur mycket RAM använder datorn?", "confidence": 0.80},
        {"text": "Hur mycket ram använder min dator?", "confidence": 0.81},
        {"text": "Stäng av lampan", "confidence": 0.99},
    ])
    assert r["accepted"] is True
    assert r["support"] == 2
    assert "ram" in r["text"].lower()
    assert "Stäng av" not in r["text"]



def test_high_confidence_single_confirm_cannot_execute_destructive_command():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    assert pipeline.process_utterance(b"danger")["status"] == "confirmation_required"
    primary.result = {"text": "bekräfta", "confidence": 1.0}
    result = pipeline.process_utterance(b"confirm")
    assert result["status"] == "confirmation_required"
    assert result["confirmation_confidence"] == 1.0
    assert assistant.messages == []
    assert pipeline.pending_confirmation is not None


def test_two_independent_confirmation_votes_from_three_may_confirm():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "bekräfta", "confidence": 0.99}
    pipeline.backup_stt[0].result = {
        "text": "bekräfta kommandot", "confidence": 0.91,
    }
    pipeline.backup_stt[1].result = {"text": "bakgrundsljud", "confidence": 0.99}
    result = pipeline.process_utterance(b"confirmation")
    assert result["status"] == "completed"
    assert result["confirmation"]["support"] == 2
    assert assistant.messages == ["Radera filen rapport txt"]


def test_any_backup_cancel_vetoes_two_high_confidence_confirmations():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "bekräfta", "confidence": 0.99}
    pipeline.backup_stt[0].result = {"text": "bekräfta", "confidence": 0.95}
    pipeline.backup_stt[1].result = {"text": "avbryt", "confidence": 0.70}
    result = pipeline.process_utterance(b"confirmation")
    assert result["status"] == "confirmation_cancelled"
    assert pipeline.pending_confirmation is None
    assert assistant.messages == []


def test_any_backup_explicit_negation_vetoes_confirmation():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "bekräfta", "confidence": 0.99}
    pipeline.backup_stt[0].result = {"text": "bekräfta", "confidence": 0.99}
    pipeline.backup_stt[1].result = {"text": "bekräfta inte", "confidence": 0.97}
    result = pipeline.process_utterance(b"confirmation")
    assert result["status"] == "confirmation_required"
    assert pipeline.pending_confirmation is not None
    assert assistant.messages == []


def test_two_duplicate_confirming_recognizers_cannot_make_three_votes():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "bekräfta", "confidence": 1.0}
    duplicate = FakeSTT({"text": "bekräfta", "confidence": 1.0})
    pipeline.backup_stt = [duplicate, duplicate]
    result = pipeline.process_utterance(b"confirmation")
    assert result["status"] == "confirmation_required"
    assert duplicate.calls == 1
    assert assistant.messages == []


def test_primary_as_backup_cannot_make_three_confirmation_votes():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "bekräfta", "confidence": 1.0}
    independent = FakeSTT({"text": "bekräfta", "confidence": 0.99})
    pipeline.backup_stt = [primary, independent]
    result = pipeline.process_utterance(b"confirmation")
    assert result["status"] == "confirmation_required"
    assert primary.calls == 2
    assert independent.calls == 1
    assert assistant.messages == []


def test_stt_failure_during_confirmation_is_not_authorization():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "bekräfta", "confidence": 0.99}
    class FailingBackup:
        def transcribe(self, audio):
            raise RuntimeError("SECRET_ACCOUNT_DATA")
    pipeline.backup_stt = [
        FailingBackup(), FakeSTT({"text": "bekräfta", "confidence": 0.99}),
    ]
    result = pipeline.process_utterance(b"confirmation")
    assert result["status"] == "confirmation_required"
    assert "SECRET_ACCOUNT_DATA" not in str(result)
    assert assistant.messages == []


def test_confirmation_expiring_during_backup_stt_never_executes():
    clock = FakeClock()
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=clock)
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "bekräfta", "confidence": 0.99}
    class SlowBackup:
        def transcribe(self, audio):
            clock.advance(16)
            return {"text": "bekräfta", "confidence": 0.99}
    pipeline.backup_stt = [
        SlowBackup(), FakeSTT({"text": "bekräfta", "confidence": 0.99}),
    ]
    result = pipeline.process_utterance(b"confirmation")
    assert result["status"] == "confirmation_expired"
    assert pipeline.pending_confirmation is None
    assert assistant.messages == []


def test_no_independent_confirmation_backups_never_override_confidence():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "bekräfta", "confidence": 1.0}
    pipeline.backup_stt = []
    result = pipeline.process_utterance(b"confirmation")
    assert result["status"] == "confirmation_required"
    assert assistant.messages == []


def test_primary_cancel_still_immediately_clears_pending_action():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    pipeline.process_utterance(b"danger")
    primary.result = {"text": "avbryt", "confidence": 0.6}
    result = pipeline.process_utterance(b"cancel")
    assert result["status"] == "confirmation_cancelled"
    assert pipeline.pending_confirmation is None
    assert assistant.messages == []



class ChangingVoiceToolPlanner(FakeAssistant):
    def __init__(self, clock=None):
        super().__init__()
        self.selected = "workspace_write"
        self.fail = False
        self.invalid = False
        self.plan_input = None
        self.preview_calls = 0
        self.expire_on_preview = None
        self.clock = clock
        self.tools = {
            "workspace_write": {
                "safety": {"effect": "write", "voice_confirmation_required": True}
            },
            "workspace_delete": {
                "safety": {"effect": "destructive", "voice_confirmation_required": True}
            },
        }

    def preview_tool_plan(self, message):
        self.preview_calls += 1
        if self.expire_on_preview == self.preview_calls and self.clock:
            self.clock.advance(16)
        if self.fail:
            raise RuntimeError("SECRET_SENSITIVE_PLANNER_ERROR")
        if self.invalid:
            return {"steps": None}
        return {"steps": [{"tool": self.selected,
                            "input": message if self.plan_input is None
                            else self.plan_input}]}


def make_voice_planner_confirmation(planner, clock=None):
    primary = FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99})
    backups = [
        FakeSTT({"text": "Skapa filen test txt", "confidence": 0.98}),
        FakeSTT({"text": "Skapa filen test txt", "confidence": 0.97}),
    ]
    pipeline = VoicePipeline(
        planner, primary, backup_stt=backups,
        clock=clock,
        settings=settings(high_risk_confirmation_enabled=True),
    )
    initial = pipeline.process_utterance(b"synthetic-command")
    assert initial["status"] == "confirmation_required"
    assert planner.messages == []
    primary.result = {"text": "bekräfta", "confidence": 0.99}
    for backup in backups:
        backup.result = {"text": "bekräfta", "confidence": 0.99}
    return pipeline


def test_highrisk_planner_error_at_first_command_must_not_create_pending():
    planner = ChangingVoiceToolPlanner()
    planner.fail = True
    primary = FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99})
    backups = [
        FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99}),
        FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99}),
    ]
    pipeline = VoicePipeline(
        planner, primary, backup_stt=backups,
        settings=settings(high_risk_confirmation_enabled=True),
    )
    result = pipeline.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert pipeline.pending_confirmation is None
    assert planner.messages == []
    assert "SECRET" not in str(result)


def test_planner_failing_at_confirm_never_reuses_empty_tool_lists():
    planner = ChangingVoiceToolPlanner()
    pipeline = make_voice_planner_confirmation(planner)
    planner.fail = True
    result = pipeline.process_utterance(b"synthetic-confirm")
    assert result["status"] == "confirmation_cancelled"
    assert pipeline.pending_confirmation is None
    assert planner.messages == []
    assert "SECRET" not in str(result)


def test_tool_switch_after_initial_voice_consent_cancels_not_reconfirms():
    planner = ChangingVoiceToolPlanner()
    pipeline = make_voice_planner_confirmation(planner)
    planner.selected = "workspace_delete"
    result = pipeline.process_utterance(b"synthetic-confirm")
    assert result["status"] == "confirmation_cancelled"
    assert pipeline.pending_confirmation is None
    assert planner.messages == []


def test_planner_downgraded_to_readonly_before_confirmation_is_not_accepted():
    planner = ChangingVoiceToolPlanner()
    pipeline = make_voice_planner_confirmation(planner)
    planner.tools["workspace_write"]["safety"] = {
        "effect": "read_only", "voice_confirmation_required": False
    }
    result = pipeline.process_utterance(b"synthetic-confirm")
    assert result["status"] == "confirmation_cancelled"
    assert planner.messages == []


def test_same_tool_but_safety_effect_mutation_cancels_pending():
    planner = ChangingVoiceToolPlanner()
    pipeline = make_voice_planner_confirmation(planner)
    # Risk still classifies high and the tool NAME is unchanged.
    planner.tools["workspace_write"]["safety"]["effect"] = "destructive"
    result = pipeline.process_utterance(b"synthetic-confirm")
    assert result["status"] == "confirmation_cancelled"
    assert pipeline.pending_confirmation is None
    assert planner.messages == []


def test_planner_disappearing_after_first_command_cancels_pending():
    planner = ChangingVoiceToolPlanner()
    pipeline = make_voice_planner_confirmation(planner)
    planner.preview_tool_plan = None
    result = pipeline.process_utterance(b"synthetic-confirm")
    assert result["status"] == "confirmation_cancelled"
    assert planner.messages == []


def test_planner_malformed_first_result_requires_clarification():
    planner = ChangingVoiceToolPlanner()
    planner.invalid = True
    primary = FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99})
    pipeline = VoicePipeline(
        planner, primary,
        backup_stt=[
            FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99}),
            FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99}),
        ],
        settings=settings(high_risk_confirmation_enabled=True),
    )
    result = pipeline.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert pipeline.pending_confirmation is None
    assert planner.messages == []


def test_confirmation_expiring_during_plan_recheck_never_executes():
    clock = FakeClock()
    planner = ChangingVoiceToolPlanner(clock=clock)
    pipeline = make_voice_planner_confirmation(planner, clock=clock)
    assert planner.preview_calls == 2
    planner.expire_on_preview = 3
    result = pipeline.process_utterance(b"synthetic-confirm")
    assert result["status"] == "confirmation_expired"
    assert pipeline.pending_confirmation is None
    assert planner.messages == []


def test_unchanged_planner_with_independent_confirmation_executes_once():
    planner = ChangingVoiceToolPlanner()
    pipeline = make_voice_planner_confirmation(planner)
    result = pipeline.process_utterance(b"synthetic-confirm")
    assert result["status"] == "completed"
    assert planner.messages == ["Skapa filen test txt"]
    assert result["confirmation"]["confirmed"] is True


def test_lowrisk_question_without_planner_still_works():
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant, FakeSTT({"text": "Hur är vädret", "confidence": 0.99}),
        settings=settings(),
    )
    result = pipeline.process_utterance(b"synthetic-lowrisk")
    assert result["status"] == "completed"
    assert assistant.messages == ["Hur är vädret"]



def test_same_tool_but_changed_target_argument_cancels_pending():
    planner = ChangingVoiceToolPlanner()
    pipeline = make_voice_planner_confirmation(planner)
    planner.plan_input = "Radera filen annan-anvandare"
    result = pipeline.process_utterance(b"synthetic-confirm")
    assert result["status"] == "confirmation_cancelled"
    assert pipeline.pending_confirmation is None
    assert planner.messages == []
    assert "annan-anvandare" not in str(result)


def test_private_tool_plan_signature_does_not_publish_arguments():
    planner = ChangingVoiceToolPlanner()
    planner.plan_input = "private confidential value test@example.invalid"
    pipeline = make_voice_planner_confirmation(planner)
    pending = pipeline.pending_confirmation
    assert pending is not None
    risk = pending["risk"]
    assert len(risk["tool_plan_digest"]) == 64
    assert "test@example.invalid" not in str(risk)
    assert "private confidential" not in str(risk)
    # Different sessions use distinct secret HMAC keys for same plan.
    planner2 = ChangingVoiceToolPlanner()
    planner2.plan_input = planner.plan_input
    another = make_voice_planner_confirmation(planner2)
    assert risk["tool_plan_digest"] != another.pending_confirmation[
        "risk"
    ]["tool_plan_digest"]


def test_malformed_planner_arguments_never_make_unverifiable_signature():
    planner = ChangingVoiceToolPlanner()
    planner.plan_input = object()
    primary = FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99})
    pipeline = VoicePipeline(
        planner, primary,
        backup_stt=[
            FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99}),
            FakeSTT({"text": "Skapa filen test txt", "confidence": 0.99}),
        ],
        settings=settings(high_risk_confirmation_enabled=True),
    )
    result = pipeline.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert pipeline.pending_confirmation is None
    assert planner.messages == []


def test_semantic_fallback_cannot_promote_one_dangerous_asr_outlier_to_action():
    assistant = FakeAssistant()
    resolver = FakeSemanticResolver({
        "accepted": True,
        "text": "Radera filen rapport.txt",
        "selected_index": 2,
        "supporting_indices": [0, 2],
        "support": 2,
        "confidence": 0.99,
        "reason": "Same intent",  # This is not a reliable risk vote.
    })
    pipeline = VoicePipeline(
        assistant,
        FakeSTT({"text": "Hur mår processorn?", "confidence": 0.2}),
        backup_stt=[
            FakeSTT({"text": "Vilket datum är det?", "confidence": 0.2}),
            FakeSTT({"text": "Radera filen rapport.txt", "confidence": 0.2}),
        ],
        settings=settings(semantic_consensus_enabled=True),
        semantic_resolver=resolver,
    )

    result = pipeline.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert result["risk"]["level"] == "high"
    assert result["consensus"]["method"] == "semantic"
    assert result["consensus"]["accepted"] is False
    assert assistant.messages == []
    assert len(resolver.calls) == 1


def test_semantic_low_risk_fallback_remains_available():
    assistant = FakeAssistant()
    resolver = FakeSemanticResolver({
        "accepted": True,
        "text": "Hur mycket RAM används?",
        "selected_index": 1,
        "supporting_indices": [0, 1],
        "support": 2,
        "confidence": 0.95,
    })
    pipeline = VoicePipeline(
        assistant,
        FakeSTT({"text": "Minnets last?", "confidence": 0.2}),
        backup_stt=[
            FakeSTT({"text": "Hur mycket RAM används?", "confidence": 0.2}),
            FakeSTT({"text": "Vilken dag?", "confidence": 0.2}),
        ],
        settings=settings(semantic_consensus_enabled=True),
        semantic_resolver=resolver,
    )
    result = pipeline.process_utterance(b"synthetic")
    assert result["status"] == "completed"
    assert assistant.messages == ["Hur mycket RAM används?"]



def test_primary_asr_provider_exception_is_clarify_not_handsfree_crash():
    class BrokenPrimary:
        def transcribe(self, audio):
            raise RuntimeError("SECRET_MICROPHONE_CREDENTIAL")
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant, BrokenPrimary(),
        backup_stt=[
            FakeSTT({"text": "Radera filen", "confidence": 1.0}),
            FakeSTT({"text": "Radera filen", "confidence": 1.0}),
        ],
        settings=settings(high_risk_confirmation_enabled=True),
    )
    result = pipeline.process_utterance(b"PRIVATE_AUDIO")
    assert result["status"] == "clarify"
    assert assistant.messages == []
    assert pipeline.pending_confirmation is None
    assert "SECRET" not in str(result)
    assert "PRIVATE_AUDIO" not in str(result)


def test_one_failed_independent_stt_skipped_when_other_valid_backups_exist():
    class BrokenBackup:
        def transcribe(self, audio):
            raise TimeoutError("SECRET_STT_DEBUG_STACK")
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant, FakeSTT({"text": "Visa RAM-status", "confidence": 0.1}),
        backup_stt=[
            BrokenBackup(),
            FakeSTT({"text": "Visa RAM-status", "confidence": 0.85}),
            FakeSTT({"text": "Visa RAM-status", "confidence": 0.8}),
        ],
        settings=settings(redundant_transcript_count=3),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "completed"
    assert result["consensus"]["support"] == 3
    assert assistant.messages == ["Visa RAM-status"]
    assert "SECRET" not in str(result)


def test_high_risk_empty_backup_cannot_count_as_independent_vote():
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant, FakeSTT({"text": "Radera rapporten", "confidence": 1.0}),
        backup_stt=[
            FakeSTT({"text": "", "confidence": 1.0}),
            FakeSTT({"text": "Radera rapporten", "confidence": 1.0}),
        ],
        settings=settings(),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "clarify"
    assert "inte tillräckligt många" in result["message"]
    assert assistant.messages == []


def test_failed_backup_without_replacement_does_not_authorize_action():
    class BrokenBackup:
        def transcribe(self, audio):
            raise OSError("SECRET_DEVICE_ID")
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant, FakeSTT({"text": "Radera rapporten", "confidence": 1.0}),
        backup_stt=[
            FakeSTT({"text": "Radera rapporten", "confidence": 1.0}),
            BrokenBackup(),
        ],
        settings=settings(),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "clarify"
    assert assistant.messages == []
    assert "SECRET" not in str(result)


def test_confirmation_skip_failed_backup_but_require_three_valid_votes():
    class BrokenBackup:
        def transcribe(self, audio):
            raise OSError("PRIVATE_STT_FAILURE")
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    first = pipeline.process_utterance(b"danger")
    assert first["status"] == "confirmation_required"
    primary.result = {"text": "bekräfta", "confidence": 1.0}
    pipeline.backup_stt = [
        BrokenBackup(),
        FakeSTT({"text": "bekräfta", "confidence": 0.99}),
        FakeSTT({"text": "bekräfta", "confidence": 0.99}),
    ]
    confirm = pipeline.process_utterance(b"confirm")
    assert confirm["status"] == "completed"
    assert confirm["confirmation"]["support"] == 3
    assert assistant.messages == ["Radera filen rapport txt"]
    assert "PRIVATE_STT_FAILURE" not in str(confirm)


def test_confirmation_blank_backup_does_not_authorize_with_only_two_votes():
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=FakeClock())
    assert pipeline.process_utterance(b"danger")["status"] == "confirmation_required"
    primary.result = {"text": "bekräfta", "confidence": 0.99}
    pipeline.backup_stt = [
        FakeSTT({"text": "", "confidence": 1.0}),
        FakeSTT({"text": "bekräfta", "confidence": 1.0}),
    ]
    confirm = pipeline.process_utterance(b"confirm")
    assert confirm["status"] == "confirmation_required"
    assert pipeline.pending_confirmation is not None
    assert assistant.messages == []


def test_primary_stt_late_return_cannot_dispatch_or_retain_consent():
    clock = FakeClock()
    pipeline, assistant, primary, _ = high_risk_pipeline(clock=clock)
    assert pipeline.process_utterance(b"danger")["status"] == "confirmation_required"

    class SlowPrimary:
        def transcribe(self, audio):
            clock.advance(46)
            return {"text": "bekräfta", "confidence": 1.0}
    pipeline.primary_stt = SlowPrimary()
    confirm = pipeline.process_utterance(b"confirm")
    assert confirm["status"] == "clarify"
    assert "för lång tid" in confirm["message"]
    assert pipeline.pending_confirmation is None
    assert assistant.messages == []


def test_backup_stt_late_return_cannot_dispatch_nonconfirmed_tool_action():
    clock = FakeClock()
    assistant = FakeAssistant()
    class SlowBackup:
        def transcribe(self, audio):
            clock.advance(46)
            return {"text": "Visa RAM", "confidence": 0.99}
    pipeline = VoicePipeline(
        assistant, FakeSTT({"text": "Visa RAM", "confidence": 0.1}),
        backup_stt=[
            SlowBackup(),
            FakeSTT({"text": "Visa RAM", "confidence": 0.99}),
        ],
        clock=clock,
        settings=settings(),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "clarify"
    assert assistant.messages == []


def test_small_configured_stt_budget_prevents_stale_highrisk_action():
    clock = FakeClock()
    class SlowPrimary:
        def transcribe(self, audio):
            clock.advance(2)
            return {"text": "Radera filen", "confidence": 1.0}
    assistant = FakeAssistant()
    pipeline = VoicePipeline(
        assistant, SlowPrimary(), clock=clock,
        settings=settings(stt_observed_budget_seconds=1.0),
    )
    assert pipeline.process_utterance(b"fake")["status"] == "clarify"
    assert assistant.messages == []


def test_invalid_stt_deadline_setting_always_blocks_dispatch():
    assistant = FakeAssistant()
    for bad in (None, False, "45", float("nan"), float("inf"), -1, 0, 1000):
        pipeline = VoicePipeline(
            assistant, FakeSTT({"text": "Hej", "confidence": 1.0}),
            settings=settings(stt_observed_budget_seconds=bad),
        )
        assert pipeline.process_utterance(b"fake")["status"] == "clarify"
    assert assistant.messages == []
