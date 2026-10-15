import pytest

from core.voice_session import VoiceSession


class FakeMicrophone:
    def __init__(self, frames):
        self.frames = list(frames)
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        return True

    def read_frame(self):
        if not self.frames:
            return {
                "frame": b"z",
                "overflowed": False,
            }

        return self.frames.pop(0)

    def stop(self):
        self.stopped = True
        self.started = False
        return True


class FakeVAD:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def is_speech(self, frame):
        if not self.decisions:
            return False

        return self.decisions.pop(0)


class FakeSTT:
    def __init__(self, text="Hej"):
        self.text = text
        self.audio = []

    def transcribe(self, audio):
        self.audio.append(audio)
        return {
            "text": self.text,
            "confidence": 0.99,
        }


class FakeTTS:
    def __init__(self):
        self.spoken = []
        self.stop_calls = 0

    def speak(self, text):
        self.spoken.append(text)

    def stop(self):
        self.stop_calls += 1
        return True


class FakeAssistant:
    def __init__(self):
        self.messages = []
        self.llm = object()

    def respond(self, message):
        self.messages.append(message)
        return {
            "answer": "Svar",
            "tools": [],
            "tool_results": {},
        }


def settings(enabled=True, tts=False, **overrides):
    voice = {
            "enabled": enabled,
            "tts_enabled": tts,
            "redundancy_enabled": True,
            "redundancy_when_confidence_missing": False,
            "primary_confidence_threshold": 0.72,
            "consensus_similarity_threshold": 0.62,
            "redundant_transcript_count": 3,
            "vad_start_speech_frames": 1,
            "vad_end_silence_frames": 2,
            "vad_max_frames": 20,
            "session_max_wait_frames": 20,
            "semantic_consensus_enabled": False,
            "semantic_consensus_min_confidence": 0.85,
        }
    voice.update(overrides)
    return {
        "voice": voice,
    }


def components(
    microphone,
    vad,
    stt=None,
    tts=None,
    enabled=True,
):
    return {
        "enabled": enabled,
        "microphone": microphone,
        "vad": vad,
        "primary_stt": stt or FakeSTT(),
        "backup_stt": [],
        "tts": tts,
    }


def test_disabled_session_reports_disabled():
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(enabled=False),
        components={
            "enabled": False,
            "microphone": None,
            "vad": None,
            "primary_stt": None,
            "backup_stt": [],
            "tts": None,
        },
    )

    assert session.status() == {
        "enabled": False,
        "running": False,
    }
    assert session.run_once()["status"] == "disabled"


def test_run_once_executes_full_voice_path():
    mic = FakeMicrophone(
        [
            {
                "frame": b"a",
                "overflowed": False,
            },
            {
                "frame": b"b",
                "overflowed": False,
            },
            {
                "frame": b"c",
                "overflowed": False,
            },
        ]
    )
    vad = FakeVAD(
        [True, False, False]
    )
    stt = FakeSTT(
        "Hur mycket RAM används?"
    )
    assistant = FakeAssistant()
    session = VoiceSession(
        assistant,
        settings=settings(),
        components=components(
            mic,
            vad,
            stt=stt,
        ),
    )

    result = session.run_once()

    assert result["status"] == "utterance_complete"
    assert result["end_reason"] == "silence"
    assert result["voice_result"]["status"] == "completed"
    assert assistant.messages == [
        "Hur mycket RAM används?"
    ]
    assert stt.audio == [b"abc"]
    assert session.running is True


def test_run_once_counts_microphone_overflow():
    mic = FakeMicrophone(
        [
            {
                "frame": b"a",
                "overflowed": True,
            },
            {
                "frame": b"b",
                "overflowed": False,
            },
            {
                "frame": b"c",
                "overflowed": False,
            },
        ]
    )
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(),
        components=components(
            mic,
            FakeVAD(
                [True, False, False]
            ),
        ),
    )

    result = session.run_once()

    assert result["overflow_count"] == 1


def test_run_once_times_out_without_complete_utterance():
    mic = FakeMicrophone(
        [
            {
                "frame": b"a",
                "overflowed": False,
            }
            for _ in range(4)
        ]
    )
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(),
        components=components(
            mic,
            FakeVAD(
                [False, False, False, False]
            ),
        ),
    )

    result = session.run_once(
        max_wait_frames=4
    )

    assert result["status"] == "timeout"
    assert result["frames_read"] == 4


def test_stop_closes_microphone_and_interrupts_tts():
    mic = FakeMicrophone([])
    tts = FakeTTS()
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(tts=True),
        components=components(
            mic,
            FakeVAD([]),
            tts=tts,
        ),
    )
    session.start()

    assert session.stop() is True
    assert mic.stopped is True
    assert tts.stop_calls == 1
    assert session.running is False


def test_status_reports_provider_shapes():
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(),
        components=components(
            FakeMicrophone([]),
            FakeVAD([]),
        ),
    )

    status = session.status()

    assert status["enabled"] is True
    assert status["microphone"] == "FakeMicrophone"
    assert status["vad"] == "FakeVAD"
    assert status["primary_stt"] == "FakeSTT"
    assert status["backup_stt_count"] == 0



class TrackingMicrophone(FakeMicrophone):
    def __init__(self, frames):
        super().__init__(frames)
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1
        return super().start()

    def stop(self):
        self.stop_calls += 1
        return super().stop()


def test_ventuno_handoff_releases_microphone_before_inference():
    mic = TrackingMicrophone(
        [
            {
                "frame": b"a",
                "overflowed": False,
            },
            {
                "frame": b"b",
                "overflowed": False,
            },
            {
                "frame": b"c",
                "overflowed": False,
            },
        ]
    )
    delays = []
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(
            release_microphone_during_inference=True,
            release_stt_before_model=True,
            model_handoff_delay_seconds=1.5,
        ),
        components=components(
            mic,
            FakeVAD(
                [True, False, False]
            ),
        ),
        sleep_fn=delays.append,
    )

    result = session.run_once()

    assert result["status"] == "utterance_complete"
    assert mic.start_calls == 2
    assert mic.stop_calls == 1
    assert delays == [1.5]
    assert session.running is True
    assert (
        session.microphone_paused_for_inference
        is False
    )


def test_default_voice_profile_keeps_microphone_open_during_inference():
    mic = TrackingMicrophone(
        [
            {
                "frame": b"a",
                "overflowed": False,
            },
            {
                "frame": b"b",
                "overflowed": False,
            },
            {
                "frame": b"c",
                "overflowed": False,
            },
        ]
    )
    delays = []
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(),
        components=components(
            mic,
            FakeVAD(
                [True, False, False]
            ),
        ),
        sleep_fn=delays.append,
    )

    session.run_once()

    assert mic.start_calls == 1
    assert mic.stop_calls == 0
    assert delays == []


def test_stop_while_microphone_is_paused_does_not_restart_it():
    mic = TrackingMicrophone([])
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(
            release_microphone_during_inference=True,
        ),
        components=components(
            mic,
            FakeVAD([]),
        ),
    )
    session.start()
    session._before_inference()

    assert mic.start_calls == 1
    assert mic.stop_calls == 1
    assert session.microphone_paused_for_inference is True

    assert session.stop() is True
    assert session.running is False
    assert session.microphone_paused_for_inference is False
    assert mic.start_calls == 1
    assert mic.stop_calls == 1



class ReleasableSTT(FakeSTT):
    def __init__(self, text="Hej"):
        super().__init__(text)
        self.release_calls = 0

    def release_for_inference(self):
        self.release_calls += 1


def test_ventuno_handoff_releases_stt_provider_before_llm():
    mic = TrackingMicrophone(
        [
            {
                "frame": b"a",
                "overflowed": False,
            },
            {
                "frame": b"b",
                "overflowed": False,
            },
            {
                "frame": b"c",
                "overflowed": False,
            },
        ]
    )
    stt = ReleasableSTT(
        "Hur mycket RAM används?"
    )
    delays = []
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(
            release_microphone_during_inference=True,
            release_stt_before_model=True,
            model_handoff_delay_seconds=1.5,
        ),
        components=components(
            mic,
            FakeVAD(
                [True, False, False]
            ),
            stt=stt,
        ),
        sleep_fn=delays.append,
    )

    result = session.run_once()

    assert result["status"] == "utterance_complete"
    assert stt.release_calls == 1
    assert delays == [1.5]
    assert mic.stop_calls == 1
    assert mic.start_calls == 2



def test_default_profile_does_not_release_stt_provider_before_llm():
    mic = TrackingMicrophone(
        [
            {
                "frame": b"a",
                "overflowed": False,
            },
            {
                "frame": b"b",
                "overflowed": False,
            },
            {
                "frame": b"c",
                "overflowed": False,
            },
        ]
    )
    stt = ReleasableSTT(
        "Hur mycket RAM används?"
    )
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(
            release_microphone_during_inference=True,
            release_stt_before_model=False,
        ),
        components=components(
            mic,
            FakeVAD(
                [True, False, False]
            ),
            stt=stt,
        ),
    )

    result = session.run_once()

    assert result["status"] == "utterance_complete"
    assert stt.release_calls == 0



def test_microphone_start_false_never_marks_voice_running(monkeypatch):
    mic = TrackingMicrophone([])
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(),
        components=components(mic, FakeVAD([])),
    )
    monkeypatch.setattr(mic, "start", lambda: False)

    with pytest.raises(RuntimeError, match="kunde inte startas"):
        session.start()

    assert session.running is False
    assert session.status()["running"] is False
    assert session.microphone_paused_for_inference is False


def test_run_once_never_reads_frames_when_microphone_start_fails(monkeypatch):
    mic = FakeMicrophone([])
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(),
        components=components(mic, FakeVAD([])),
    )
    monkeypatch.setattr(mic, "start", lambda: False)
    monkeypatch.setattr(mic, "read_frame", lambda: pytest.fail(
        "Cannot read frames from a microphone that never started"
    ))

    with pytest.raises(RuntimeError, match="kunde inte startas"):
        session.run_once(max_wait_frames=1)

    assert session.running is False
    assert session.frame_count == 0


def test_microphone_start_exception_does_not_mark_session_running(monkeypatch):
    mic = FakeMicrophone([])
    session = VoiceSession(
        FakeAssistant(), settings=settings(),
        components=components(mic, FakeVAD([])),
    )
    def fail():
        raise OSError("hardware disconnected")
    monkeypatch.setattr(mic, "start", fail)

    with pytest.raises(OSError, match="hardware disconnected"):
        session.start()

    assert session.running is False


def test_microphone_stop_false_does_not_claim_stopped(monkeypatch):
    mic = FakeMicrophone([])
    session = VoiceSession(
        FakeAssistant(), settings=settings(),
        components=components(mic, FakeVAD([])),
    )
    session.start()
    original_stop = mic.stop
    monkeypatch.setattr(mic, "stop", lambda: False)

    with pytest.raises(RuntimeError, match="kunde inte stoppas"):
        session.stop()

    assert session.running is True
    assert session.status()["running"] is True
    # A working stop call can still finish cleanup after this failure.
    monkeypatch.setattr(mic, "stop", original_stop)
    assert session.stop() is True
    assert session.running is False


def test_microphone_failed_restart_keeps_paused_state_until_cleanup(monkeypatch):
    mic = TrackingMicrophone([])
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(release_microphone_during_inference=True),
        components=components(mic, FakeVAD([])),
    )
    session.start()
    assert session._before_inference() is True
    assert mic.stopped is True
    monkeypatch.setattr(mic, "start", lambda: False)

    with pytest.raises(RuntimeError, match="kunde inte återstartas"):
        session._after_inference()

    assert session.running is True
    assert session.microphone_paused_for_inference is True
    # No duplicate stop call against an already closed microphone.
    assert session.stop() is True
    assert mic.stop_calls == 1
    assert session.running is False
    assert session.microphone_paused_for_inference is False


def test_microphone_restart_exception_preserves_paused_state(monkeypatch):
    mic = FakeMicrophone([])
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(release_microphone_during_inference=True),
        components=components(mic, FakeVAD([])),
    )
    session.start()
    session._before_inference()
    def fail():
        raise OSError("device removed")
    monkeypatch.setattr(mic, "start", fail)

    with pytest.raises(OSError, match="device removed"):
        session._after_inference()

    assert session.microphone_paused_for_inference is True
    assert session.stop() is True
    assert session.running is False


def test_stop_while_paused_never_reopens_microphone(monkeypatch):
    mic = TrackingMicrophone([])
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(release_microphone_during_inference=True),
        components=components(mic, FakeVAD([])),
    )
    session.start()
    session._before_inference()
    session.stop()
    monkeypatch.setattr(mic, "start", lambda: pytest.fail(
        "Stopped session must never restart a microphone"
    ))

    assert session._after_inference() is False
    assert session.running is False
    assert session.microphone_paused_for_inference is False


def test_voice_session_stop_releases_only_opted_in_persistent_stt():
    class CachedSTT(FakeSTT):
        def __init__(self):
            super().__init__()
            self.close_calls = 0
        def close(self):
            self.close_calls += 1

    fake = CachedSTT()
    mic = FakeMicrophone([])
    components_dict = components(mic, FakeVAD([]), stt=fake)
    # Duplicate reference in backups must not be closed twice.
    components_dict["backup_stt"] = [fake]
    session = VoiceSession(
        FakeAssistant(),
        settings=settings(stt_persistent_worker_enabled=True),
        components=components_dict,
    )
    assert session.start() is True
    assert session.stop() is True
    assert fake.close_calls == 1
    assert not session.running


def test_default_voice_stop_does_not_touch_direct_stt_model():
    class DirectSTT(FakeSTT):
        def close(self):
            pytest.fail("Direct STT should not be auto-closed")
    s = VoiceSession(
        FakeAssistant(), settings=settings(),
        components=components(FakeMicrophone([]), FakeVAD([]), stt=DirectSTT())
    )
    s.start()
    assert s.stop() is True


def test_failing_persistent_cleanup_reports_generic_error_not_secret():
    class BrokenCachedSTT(FakeSTT):
        def close(self):
            raise OSError("SECRET_PRIVATE_CACHE_PATH")
    s = VoiceSession(
        FakeAssistant(),
        settings=settings(stt_persistent_worker_enabled=True),
        components=components(
            FakeMicrophone([]), FakeVAD([]), stt=BrokenCachedSTT()
        ),
    )
    s.start()
    with pytest.raises(RuntimeError) as exc:
        s.stop()
    assert "SECRET" not in str(exc.value)
    assert s.running is False



def test_voice_stop_signals_cached_stt_before_waiting_for_pipeline_cleanup():
    class Cancellable(FakeSTT):
        def __init__(self):
            super().__init__()
            self.cancel_requests = 0
            self.resume_requests = 0
            self.close_calls = 0
        def request_cancel(self):
            self.cancel_requests += 1
        def resume(self):
            self.resume_requests += 1
        def close(self):
            self.close_calls += 1

    model = Cancellable()
    components_dict = components(FakeMicrophone([]), FakeVAD([]), stt=model)
    components_dict["backup_stt"] = [model]
    s = VoiceSession(
        FakeAssistant(),
        settings=settings(stt_persistent_worker_enabled=True),
        components=components_dict,
    )
    assert s.start() is True
    assert model.resume_requests == 1
    original_interrupt = s.pipeline.interrupt
    def guarded_interrupt():
        assert model.cancel_requests == 1
        return original_interrupt()
    s.pipeline.interrupt = guarded_interrupt
    assert s.stop() is True
    assert model.close_calls == 1
    assert model.cancel_requests == 1
    assert not s.running
    assert s.start() is True
    assert model.resume_requests == 2
    assert s.stop() is True


def test_default_voice_never_requests_cancel_or_resume_on_unisolated_stt():
    class DirectProvider(FakeSTT):
        def request_cancel(self):
            pytest.fail("Direct model unexpectedly signalled")
        def resume(self):
            pytest.fail("Direct model unexpectedly resumed")
    mic = FakeMicrophone([])
    s = VoiceSession(
        FakeAssistant(), settings=settings(),
        components=components(mic, FakeVAD([]), stt=DirectProvider()),
    )
    assert s.start() is True
    assert s.stop() is True


def test_resume_pending_reap_blocks_microphone_activation():
    class PendingCleanup(FakeSTT):
        def resume(self):
            raise RuntimeError("Persistent STT cleanup pending")
    mic = FakeMicrophone([])
    s = VoiceSession(
        FakeAssistant(), settings=settings(stt_persistent_worker_enabled=True),
        components=components(mic, FakeVAD([]), stt=PendingCleanup()),
    )
    with pytest.raises(RuntimeError, match="cleanup pending"):
        s.start()
    assert mic.started is False
    assert s.running is False
