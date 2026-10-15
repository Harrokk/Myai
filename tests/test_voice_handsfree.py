import threading
import time

import pytest

from core.voice_handsfree import (
    VoiceHandsfreeRunner,
    format_handsfree_result,
)


class FakeSession:
    def __init__(
        self,
        results=None,
        enabled=True,
        error=None,
    ):
        self.enabled = enabled
        self.results = list(
            results or []
        )
        self.error = error
        self.start_calls = 0
        self.stop_calls = 0
        self.run_calls = 0
        self.running = False
        self.block = threading.Event()

    def start(self):
        self.start_calls += 1
        self.running = True
        return True

    def stop(self):
        self.stop_calls += 1
        self.running = False
        self.block.set()
        return True

    def run_once(
        self,
        max_wait_frames=None,
    ):
        self.run_calls += 1

        if self.error is not None:
            raise self.error

        if self.results:
            return self.results.pop(0)

        self.block.wait(timeout=1)
        return {
            "status": "timeout",
        }


def wait_until(predicate, timeout=1.0):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)

    return predicate()


def test_runner_processes_utterance_and_keeps_listening():
    results = []
    session = FakeSession(
        results=[
            {
                "status": "utterance_complete",
                "voice_result": {
                    "status": "completed",
                    "transcript": "Hej",
                    "assistant": {
                        "answer": "Hej tillbaka",
                    },
                },
            },
        ]
    )
    runner = VoiceHandsfreeRunner(
        session,
        on_result=results.append,
    )

    assert runner.start() is True
    assert wait_until(
        lambda: len(results) == 1
    )

    assert results[0]["status"] == "utterance_complete"
    assert runner.is_running is True

    assert runner.stop() is True
    assert session.start_calls == 1
    assert session.stop_calls >= 1


def test_timeouts_are_not_reported_as_results():
    results = []
    session = FakeSession(
        results=[
            {"status": "timeout"},
            {
                "status": "utterance_complete",
                "voice_result": {
                    "status": "completed",
                },
            },
        ]
    )
    runner = VoiceHandsfreeRunner(
        session,
        on_result=results.append,
    )

    runner.start()
    assert wait_until(
        lambda: len(results) == 1
    )
    runner.stop()

    assert len(results) == 1
    assert results[0]["status"] == "utterance_complete"


def test_runner_reports_error_and_stops():
    errors = []
    session = FakeSession(
        error=RuntimeError("mikrofonfel")
    )
    runner = VoiceHandsfreeRunner(
        session,
        on_error=errors.append,
    )

    runner.start()

    assert wait_until(
        lambda: len(errors) == 1
    )
    assert wait_until(
        lambda: not runner.is_running
    )
    assert "mikrofonfel" in str(errors[0])
    assert session.stop_calls >= 1


def test_runner_rejects_disabled_session():
    runner = VoiceHandsfreeRunner(
        FakeSession(enabled=False)
    )

    try:
        runner.start()
    except RuntimeError as error:
        assert "avstängt" in str(error)
    else:
        raise AssertionError(
            "Disabled voice should not start handsfree mode"
        )


def test_second_start_does_not_create_second_thread():
    session = FakeSession()
    runner = VoiceHandsfreeRunner(
        session
    )

    assert runner.start() is True
    assert runner.start() is False
    runner.stop()

    assert session.start_calls == 1


def test_stop_is_safe_before_start():
    session = FakeSession()
    runner = VoiceHandsfreeRunner(
        session
    )

    assert runner.stop() is True


def test_formatter_includes_transcript_and_answer():
    text = format_handsfree_result(
        {
            "status": "utterance_complete",
            "voice_result": {
                "status": "completed",
                "transcript": "Hur varmt är det?",
                "assistant": {
                    "answer": "40 grader.",
                },
            },
        }
    )

    assert "Du (röst): Hur varmt är det?" in text
    assert "AI:" in text
    assert "40 grader." in text


def test_formatter_uses_clarification_message():
    text = format_handsfree_result(
        {
            "status": "utterance_complete",
            "voice_result": {
                "status": "clarify",
                "message": "Säg kommandot igen.",
            },
        }
    )

    assert text == "Säg kommandot igen."



def test_handsfree_suppresses_ignored_echo_results():
    results = []
    session = FakeSession(
        results=[
            {
                "status": "utterance_complete",
                "voice_result": {
                    "status": "ignored_echo",
                    "transcript": "AI:s eget svar",
                },
            },
            {
                "status": "utterance_complete",
                "voice_result": {
                    "status": "completed",
                    "transcript": "Riktig fråga",
                },
            },
        ]
    )
    runner = VoiceHandsfreeRunner(
        session,
        on_result=results.append,
    )

    runner.start()
    assert wait_until(
        lambda: len(results) == 1
    )
    runner.stop()

    assert results[0]["voice_result"]["transcript"] == "Riktig fråga"



def test_formatter_returns_high_risk_confirmation_prompt():
    text = format_handsfree_result(
        {
            "status": "utterance_complete",
            "voice_result": {
                "status": "confirmation_required",
                "message": (
                    'Säg "bekräfta" för att köra eller "avbryt".'
                ),
                "transcript": "Radera filen rapport.txt",
            },
        }
    )

    assert "bekräfta" in text
    assert "avbryt" in text


def test_formatter_returns_confirmation_cancel_message():
    text = format_handsfree_result(
        {
            "status": "utterance_complete",
            "voice_result": {
                "status": "confirmation_cancelled",
                "message": "Kommandot avbröts.",
            },
        }
    )

    assert text == "Kommandot avbröts."



def test_handsfree_does_not_take_over_already_running_microphone():
    class ExternallyRunning(FakeSession):
        def start(self):
            self.start_calls += 1
            return False

    external = ExternallyRunning()
    external.running = True
    runner = VoiceHandsfreeRunner(external)

    assert runner.start() is False
    assert runner.is_running is False
    assert external.start_calls == 1
    assert external.run_calls == 0
    # Calling stop on a runner that never owned the session must NOT
    # stop someone else's active recording.
    assert runner.stop() is True
    assert external.stop_calls == 0
    assert external.running is True


def test_failed_voice_session_start_never_spawns_worker_thread():
    class FaultyStart(FakeSession):
        def start(self):
            self.start_calls += 1
            raise OSError("audio capture device unavailable")

    session = FaultyStart()
    runner = VoiceHandsfreeRunner(session)

    with pytest.raises(OSError, match="audio capture device unavailable"):
        runner.start()
    assert runner.is_running is False
    assert session.stop_calls == 0
    assert session.run_calls == 0


def test_thread_start_failure_cleans_owned_voice_session(monkeypatch):
    session = FakeSession()

    class UnavailableThread:
        def __init__(self, **kwargs):
            assert kwargs["daemon"] is True
            assert kwargs["name"] == "MyAI-VoiceHandsfree"
        def start(self):
            raise RuntimeError("thread creation rejected")

    monkeypatch.setattr("core.voice_handsfree.threading.Thread", UnavailableThread)
    runner = VoiceHandsfreeRunner(session)

    with pytest.raises(RuntimeError, match="thread creation rejected"):
        runner.start()

    assert session.start_calls == 1
    assert session.stop_calls == 1
    assert session.running is False
    assert runner._thread is None
    assert runner._owns_session is False


def test_handsfree_ownership_resets_after_normal_shutdown():
    session = FakeSession()
    runner = VoiceHandsfreeRunner(session)
    assert runner.start() is True
    assert runner.is_running is True
    assert runner._owns_session is True
    assert runner.stop() is True
    assert runner._owns_session is False


def test_refused_initial_start_does_not_block_later_valid_start():
    class ContendedSession(FakeSession):
        def start(self):
            self.start_calls += 1
            if self.start_calls == 1:
                return False
            self.running = True
            return True

    session = ContendedSession()
    runner = VoiceHandsfreeRunner(session)
    assert runner.start() is False
    assert session.stop_calls == 0
    assert runner.start() is True
    assert runner.is_running is True
    assert runner.stop() is True



def test_failed_microphone_shutdown_preserves_ownership_for_retry(monkeypatch):
    class DormantThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            pass
        def is_alive(self):
            return False
        def join(self, timeout=None):
            pass

    monkeypatch.setattr("core.voice_handsfree.threading.Thread", DormantThread)

    class FaultyStop(FakeSession):
        def stop(self):
            self.stop_calls += 1
            if self.stop_calls == 1:
                raise RuntimeError("microphone is still active")
            self.running = False
            self.block.set()
            return True

    session = FaultyStop()
    runner = VoiceHandsfreeRunner(session)
    errors = []
    runner.on_error = errors.append
    assert runner.start() is True
    # A deterministic non-running fake worker eliminates thread races;
    # stop must preserve ownership after a real capture-stop error.
    assert runner.stop() is False
    assert errors and "still active" in str(errors[0])
    assert session.stop_calls == 1
    assert session.running is True
    assert runner._owns_session is True
    assert runner.stop() is True
    assert session.running is False
    assert runner._owns_session is False


def test_thread_start_and_provider_cleanup_both_fail_keep_retry_ownership(monkeypatch):
    class FaultyStop(FakeSession):
        def stop(self):
            self.stop_calls += 1
            if self.stop_calls == 1:
                raise OSError("cannot stop capture")
            self.running = False
            return True

    class UnavailableThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            raise RuntimeError("thread unavailable")

    session = FaultyStop()
    monkeypatch.setattr("core.voice_handsfree.threading.Thread", UnavailableThread)
    runner = VoiceHandsfreeRunner(session)
    with pytest.raises(OSError, match="cannot stop capture"):
        runner.start()
    assert session.running is True
    assert runner._owns_session is True
    assert runner._thread is None
    assert runner.stop() is True
    assert session.running is False
    assert runner._owns_session is False
