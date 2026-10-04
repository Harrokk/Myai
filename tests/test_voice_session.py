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
