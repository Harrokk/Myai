import threading
import time

from core.voice_output import InterruptibleTTS


class BlockingProvider:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.spoken = []
        self.stop_calls = 0

    def speak(self, text):
        self.spoken.append(text)
        self.started.set()
        self.release.wait(timeout=2)

    def stop(self):
        self.stop_calls += 1
        self.release.set()
        return True


class FailingProvider:
    def speak(self, text):
        raise RuntimeError("tts-fel")

    def stop(self):
        return True


def test_speak_runs_in_background():
    provider = BlockingProvider()
    tts = InterruptibleTTS(
        provider,
        stop_timeout_seconds=0.5,
    )

    assert tts.speak("Hej") is True
    assert provider.started.wait(timeout=1)
    assert tts.is_speaking is True

    provider.release.set()
    assert tts.wait(timeout=1) is True
    assert provider.spoken == ["Hej"]


def test_stop_interrupts_underlying_provider():
    provider = BlockingProvider()
    tts = InterruptibleTTS(
        provider,
        stop_timeout_seconds=1,
    )
    tts.speak("Långt svar")
    assert provider.started.wait(timeout=1)

    assert tts.stop() is True
    assert provider.stop_calls == 1
    assert tts.is_speaking is False


def test_empty_text_is_ignored():
    tts = InterruptibleTTS(
        BlockingProvider()
    )

    assert tts.speak("   ") is False
    assert tts.is_speaking is False


def test_background_error_is_recorded():
    tts = InterruptibleTTS(
        FailingProvider()
    )

    tts.speak("Hej")
    assert tts.wait(timeout=1) is True

    status = tts.status()
    assert status["is_speaking"] is False
    assert "tts-fel" in status["last_error"]


def test_new_speech_stops_previous_speech():
    provider = BlockingProvider()
    tts = InterruptibleTTS(
        provider,
        stop_timeout_seconds=1,
    )

    tts.speak("Första")
    assert provider.started.wait(timeout=1)

    # Första stop() frigör providern innan nästa tråd startas.
    assert tts.speak("Andra") is True

    deadline = time.time() + 1

    while len(provider.spoken) < 2 and time.time() < deadline:
        time.sleep(0.01)

    assert provider.stop_calls >= 1
    assert provider.spoken == [
        "Första",
        "Andra",
    ]

    provider.release.set()
    tts.wait(timeout=1)


def test_status_reports_wrapped_provider():
    provider = BlockingProvider()
    tts = InterruptibleTTS(provider)

    assert tts.status()["provider"] == "BlockingProvider"
