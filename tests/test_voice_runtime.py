from modules.voice.runtime import VoiceRuntime


class FakeAssistant:
    def respond(self, text):
        return {
            "answer": text,
            "tools": [],
            "tool_results": {},
        }


class FakeMicrophone:
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.stream = None

    def start(self):
        self.started += 1
        self.stream = object()
        return True

    def stop(self):
        self.stopped += 1

        if self.stream is None:
            return False

        self.stream = None
        return True


class FakeSession:
    def __init__(self):
        self.interrupts = 0

    def interrupt(self):
        self.interrupts += 1
        return {
            "stopped": self.interrupts > 0,
            "reason": "test",
        }


def settings(enabled=True):
    return {
        "voice": {
            "enabled": enabled,
        }
    }


def test_disabled_runtime_does_not_start_microphone():
    microphone = FakeMicrophone()
    runtime = VoiceRuntime(
        FakeAssistant(),
        settings(enabled=False),
        stt_engines=[object()],
        tts_engine=None,
        session=FakeSession(),
        controller=object(),
        microphone=microphone,
    )

    result = runtime.start()

    assert result["started"] is False
    assert microphone.started == 0


def test_runtime_requires_microphone():
    runtime = VoiceRuntime(
        FakeAssistant(),
        settings(),
        stt_engines=[object()],
        tts_engine=None,
        session=FakeSession(),
        controller=object(),
        microphone=None,
    )
    runtime.microphone = None

    result = runtime.start()

    assert result["started"] is False
    assert "mikrofon" in result["reason"].lower()


def test_runtime_requires_stt_engine():
    microphone = FakeMicrophone()
    runtime = VoiceRuntime(
        FakeAssistant(),
        settings(),
        stt_engines=[],
        tts_engine=None,
        session=FakeSession(),
        controller=object(),
        microphone=microphone,
    )

    result = runtime.start()

    assert result["started"] is False
    assert "STT" in result["reason"]


def test_runtime_start_and_stop_manage_lifecycle():
    microphone = FakeMicrophone()
    session = FakeSession()
    runtime = VoiceRuntime(
        FakeAssistant(),
        settings(),
        stt_engines=[object()],
        tts_engine=object(),
        session=session,
        controller=object(),
        microphone=microphone,
    )

    start = runtime.start()
    stop = runtime.stop()

    assert start["started"] is True
    assert microphone.started == 1
    assert stop["stopped"] is True
    assert microphone.stopped == 1
    assert session.interrupts == 1
    assert runtime.running is False


def test_runtime_collects_completed_frame_results():
    runtime = VoiceRuntime(
        FakeAssistant(),
        settings(enabled=False),
        stt_engines=[],
        tts_engine=None,
        session=FakeSession(),
        controller=object(),
        microphone=FakeMicrophone(),
    )

    runtime._on_frame_result(
        {
            "completed": False,
            "event": "speech",
        }
    )
    runtime._on_frame_result(
        {
            "completed": True,
            "event": "speech_end",
            "session_result": {
                "status": "completed",
            },
        }
    )

    assert len(runtime.completed_results) == 1
    assert (
        runtime.completed_results[0]["session_result"]["status"]
        == "completed"
    )


def test_runtime_status_reports_components():
    runtime = VoiceRuntime(
        FakeAssistant(),
        settings(),
        stt_engines=[object(), object()],
        tts_engine=object(),
        session=FakeSession(),
        controller=object(),
        microphone=FakeMicrophone(),
    )

    status = runtime.status()

    assert status["enabled"] is True
    assert status["microphone_configured"] is True
    assert status["stt_engine_count"] == 2
    assert status["tts_configured"] is True
