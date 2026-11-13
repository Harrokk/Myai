"""Entirely synthetic; no physical input, voice model, microphone or speaker."""
from threading import Event, Thread

import pytest

from core.app_lab_voice_handoff import AppLabFinalTextHandoff


class FakeCore:
    def __init__(self, response=None):
        self.response = response or {
            "answer": "Hej från MyAI", "tool_execution_status": "not_applicable",
            "manual_reconciliation_required": False,
            "tool_dispatch_blocked": False,
        }
        self.calls = []

    def respond_voice(self, text, *, plan_verifier):
        self.calls.append((text, plan_verifier))
        return self.response


def run(handoff, text="Vad heter du?", **patch):
    args = {"session_active": True, "asr_released": True,
            "stop_requested": lambda: False}
    args.update(patch)
    return handoff.dispatch(text, **args)


def test_disabled_by_default_does_not_call_core():
    core = FakeCore()
    assert run(AppLabFinalTextHandoff(core)) == {"status": "disabled"}
    assert core.calls == []


def test_valid_final_calls_core_once_and_forbids_effectful_plan_approval():
    core = FakeCore()
    bridge = AppLabFinalTextHandoff(core, enabled=True)
    output = run(bridge, "  Vad heter du?  ")
    assert output["status"] == "answer-ready"
    assert output["answer"] == "Hej från MyAI"
    assert len(core.calls) == 1
    text, verifier = core.calls[0]
    assert text == "Vad heter du?"
    assert verifier({"steps": [{"tool": "delete_all"}]}, {}) is False
    assert verifier.voice_stop_requested() is False
    assert run(bridge)["status"] == "already-consumed"
    assert len(core.calls) == 1


@pytest.mark.parametrize("patch,expected", [
    ({"session_active": False}, "not-authorized-or-audio-active"),
    ({"asr_released": False}, "not-authorized-or-audio-active"),
    ({"stop_requested": None}, "missing-stop-probe"),
    ({"stop_requested": lambda: True}, "cancelled"),
    ({"stop_requested": lambda: None}, "cancelled"),
])
def test_fail_closed_session_requirements(patch, expected):
    core = FakeCore()
    assert run(AppLabFinalTextHandoff(core, enabled=True), **patch) == {
        "status": expected}
    assert core.calls == []


@pytest.mark.parametrize("text", ["", "  ", None, 12, "a" * 501,
                                   "secret\x00prompt", "hi\nworld"])
def test_reject_invalid_transcript_without_calling_core(text):
    core = FakeCore()
    assert run(AppLabFinalTextHandoff(core, enabled=True), text)["status"] == "invalid-final-text"
    assert core.calls == []


def test_backend_exception_redacted():
    class LeakyCore:
        def respond_voice(self, *a, **kw):
            raise RuntimeError("PRIVATE SPOKEN WORDS AND PATH")
    assert run(AppLabFinalTextHandoff(LeakyCore(), enabled=True)) == {
        "status": "voice-responder-failed"}


def test_race_stop_after_backend_response_suppresses_answer():
    stopped = Event()
    class StopCore:
        def respond_voice(self, text, *, plan_verifier):
            stopped.set()
            return {"answer": "PRIVATE OUTPUT"}
    result = run(AppLabFinalTextHandoff(StopCore(), enabled=True),
                 stop_requested=stopped.is_set)
    assert result == {"status": "cancelled"}


def test_manual_reconciliation_and_blocked_tools_do_not_become_success():
    for response, expected in [
        ({"answer": "Kontrollera manuellt", "tool_execution_status": "unknown"},
         "review-required"),
        ({"answer": "Ingen ändring gjord", "tool_execution_status": "blocked",
          "tool_dispatch_blocked": True}, "tool-dispatch-blocked")]:
        result = run(AppLabFinalTextHandoff(FakeCore(response), enabled=True))
        assert result["status"] == expected
        assert "answer" in result


def test_concurrent_duplicate_delivery_only_calls_core_once():
    core = FakeCore()
    handoff = AppLabFinalTextHandoff(core, enabled=True)
    outcomes = []
    workers = [Thread(target=lambda: outcomes.append(run(handoff))) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(3)
    assert len(core.calls) == 1
    assert sum(r["status"] == "answer-ready" for r in outcomes) == 1
    assert sum(r["status"] == "already-consumed" for r in outcomes) == 7


def test_never_imports_hardware_or_starts_services():
    import inspect
    import core.app_lab_voice_handoff as m
    source = inspect.getsource(m)
    for banned in ("import sounddevice", "from arduino", "subprocess.",
                   "socket.", "arecord", "aplay", "os.system"):
        assert banned not in source
