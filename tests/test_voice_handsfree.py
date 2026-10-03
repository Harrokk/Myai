import threading
import time

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
