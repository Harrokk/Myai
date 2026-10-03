import threading
import time

from core.voice_loop import ContinuousVoiceLoop


class FakeSession:
    def __init__(
        self,
        results=None,
        enabled=True,
    ):
        self.enabled = enabled
        self.results = list(
            results or []
        )
        self.started = 0
        self.stopped = 0
        self.block = threading.Event()

    def start(self):
        self.started += 1
        return True

    def stop(self):
        self.stopped += 1
        self.block.set()
        return True

    def run_once(self):
        if self.results:
            item = self.results.pop(0)

            if isinstance(item, Exception):
                raise item

            return item

        self.block.wait(timeout=0.05)
        return {
            "status": "timeout",
        }


def wait_until(predicate, timeout=1.0):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if predicate():
            return True

        time.sleep(0.01)

    return bool(predicate())


def test_loop_processes_multiple_utterances():
    results = []
    session = FakeSession(
        [
            {
                "status": "utterance_complete",
                "voice_result": {
                    "transcript": "ett",
                },
            },
            {
                "status": "utterance_complete",
                "voice_result": {
                    "transcript": "två",
                },
            },
        ]
    )
    loop = ContinuousVoiceLoop(
        session,
        on_result=results.append,
    )

    assert loop.start() is True
    assert wait_until(
        lambda: loop.utterance_count >= 2
    )

    loop.stop()

    assert len(results) == 2
    assert loop.utterance_count == 2
    assert session.started == 1
    assert session.stopped >= 1


def test_start_is_idempotent_while_running():
    session = FakeSession()
    loop = ContinuousVoiceLoop(session)

    assert loop.start() is True
    assert wait_until(
        lambda: loop.is_running
    )
    assert loop.start() is False
    loop.stop()


def test_disabled_session_refuses_start():
    loop = ContinuousVoiceLoop(
        FakeSession(enabled=False)
    )

    try:
        loop.start()
    except RuntimeError as error:
        assert "avstängt" in str(error)
    else:
        raise AssertionError(
            "Disabled voice loop should fail"
        )


def test_errors_are_isolated_and_reported():
    errors = []
    session = FakeSession(
        [
            RuntimeError("stt-fel"),
            {
                "status": "utterance_complete",
                "voice_result": {},
            },
        ]
    )
    loop = ContinuousVoiceLoop(
        session,
        on_error=errors.append,
    )

    loop.start()
    assert wait_until(
        lambda: loop.utterance_count >= 1
    )
    loop.stop()

    assert loop.error_count == 1
    assert len(errors) == 1
    assert "stt-fel" in str(errors[0])


def test_timeout_is_counted_without_stopping_loop():
    session = FakeSession(
        [
            {
                "status": "timeout",
            },
            {
                "status": "utterance_complete",
                "voice_result": {},
            },
        ]
    )
    loop = ContinuousVoiceLoop(session)

    loop.start()
    assert wait_until(
        lambda: loop.utterance_count >= 1
    )
    loop.stop()

    assert loop.timeout_count >= 1


def test_stop_unblocks_and_joins_background_loop():
    session = FakeSession()
    loop = ContinuousVoiceLoop(session)

    loop.start()
    assert wait_until(
        lambda: loop.is_running
    )

    stopped = loop.stop(
        timeout=1
    )

    assert stopped is True
    assert loop.is_running is False


def test_status_reports_counters():
    session = FakeSession()
    loop = ContinuousVoiceLoop(session)
    loop.utterance_count = 3
    loop.timeout_count = 2
    loop.error_count = 1

    assert loop.status() == {
        "running": False,
        "utterances": 3,
        "timeouts": 2,
        "errors": 1,
    }
