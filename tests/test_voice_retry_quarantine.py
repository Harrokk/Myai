"""Synthetic source-only retry protection. No physical IO or real user files."""
from copy import deepcopy

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.tool_manager import (
    EXECUTION_BLOCKED_MESSAGE,
    EXECUTION_INTERRUPTED_MESSAGE,
    run_tools,
)
from core.tool_outcome import summarize_guarded_outcomes
from core.voice_retry_quarantine import VoiceRetryQuarantine


class Memory:
    def search(self, *_args):
        return []
    def format(self, *_args):
        return "none"


class LLM:
    def __init__(self, on_chat=None):
        self.calls = 0
        self.on_chat = on_chat
    def chat(self, *_args, **_kwargs):
        self.calls += 1
        if self.on_chat is not None:
            self.on_chat()
        return "synthetic model answer"


def create_core(tmp_path, monkeypatch, tools, plan_selector, *, on_chat=None):
    import core.assistant as assistant_module
    cfg = deepcopy(DEFAULT_SETTINGS)
    cfg["memory"]["auto_assess_enabled"] = False
    core = MyAICore(cfg, tmp_path, tools=tools,
                    memory=Memory(), llm=LLM(on_chat))
    monkeypatch.setattr(
        assistant_module, "select_tool_plan",
        lambda message, *_args, **_kwargs: plan_selector(message),
    )
    return core


def verifier_for(stop):
    def verify(*_args):
        return True
    verify.voice_stop_requested = lambda: stop[0]
    return verify


def plan(tool, value="synthetic"):
    return {"source": "synthetic", "steps": [
        {"tool": tool, "input": value}
    ]}


def test_mid_write_stop_quarantines_repeated_confirmed_voice_write(
        tmp_path, monkeypatch):
    stop, writes = [False], []
    def write(value):
        writes.append(value)
        stop[0] = True
        return "SECRET_OPTIMISTIC_SUCCESS"

    core = create_core(
        tmp_path, monkeypatch,
        {"workspace_write": {
            "function": write, "pass_user_input": True,
            "safety": {"effect": "write", "voice_confirmation_required": True},
        }},
        lambda _: plan("workspace_write"),
    )
    verifier = verifier_for(stop)
    first = core.respond_voice("create synthetic file", plan_verifier=verifier)
    assert writes == ["synthetic"]
    assert first["tool_execution_status"] == "unknown"
    assert first["manual_reconciliation_required"] is True
    assert first["tool_results"]["workspace_write"] == EXECUTION_INTERRUPTED_MESSAGE

    # Explicitly simulate a NEW röstsession: fresh Stop event, identical
    # plan verification. Prior uncertainty must survive in this core.
    stop[0] = False
    again = core.respond_voice("create synthetic file", plan_verifier=verifier)
    assert writes == ["synthetic"]
    assert again["tool_results"]["workspace_write"] == EXECUTION_BLOCKED_MESSAGE
    assert again["tool_execution_status"] == "not_started"
    assert again["manual_reconciliation_required"] is True
    assert "kontrollerats manuellt" in again["answer"]


def test_quarantine_keeps_safe_status_reads_working(tmp_path, monkeypatch):
    stop, called = [False], []
    def writer():
        called.append("write")
        stop[0] = True
        return "possibly changed"
    def reader():
        called.append("read")
        return "CPU OK"
    tools = {
        "workspace_write": {"function": writer, "safety": {"effect": "write"}},
        "cpu_status": {"function": reader,
                       "safety": {"effect": "read_only"}},
    }
    core = create_core(tmp_path, monkeypatch, tools,
                       lambda message: plan("cpu_status" if "status" in message
                                            else "workspace_write"))
    verify = verifier_for(stop)
    core.respond_voice("write now", plan_verifier=verify)
    stop[0] = False
    read = core.respond_voice("get status", plan_verifier=verify)
    assert read["tool_execution_status"] == "completed"
    assert read["tool_results"]["cpu_status"] == "CPU OK"
    assert called == ["write", "read"]
    assert core._voice_retry_quarantine.review_required


def test_failed_effectful_callback_requires_review_before_voice_retry(
        tmp_path, monkeypatch):
    called = []
    def bad():
        called.append("attempted")
        raise RuntimeError("SECRET_FAILURE")
    core = create_core(
        tmp_path, monkeypatch,
        {"workspace_write": {"function": bad,
                              "safety": {"effect": "write"}}},
        lambda _: plan("workspace_write"),
    )
    verify = verifier_for([False])
    first = core.respond_voice("write", plan_verifier=verify)
    assert first["tool_execution_status"] == "failed"
    assert core._voice_retry_quarantine.review_required
    second = core.respond_voice("write", plan_verifier=verify)
    assert called == ["attempted"]
    assert second["tool_dispatch_blocked"]
    assert second["manual_reconciliation_required"] is True


def test_prior_write_succeeded_then_later_failure_also_requires_review():
    guard = VoiceRetryQuarantine()
    tools = {
        "workspace_write": {"function": lambda: "done",
                            "safety": {"effect": "write"}},
        "cpu_status": {"function": lambda: "fail",
                       "safety": {"effect": "read_only"}},
    }
    outcomes = {
        "workspace_write": {"state": "succeeded", "attempted": True},
        "cpu_status": {"state": "failed", "attempted": True},
    }
    assert summarize_guarded_outcomes(outcomes) == "partially_completed"
    guard.observe(["workspace_write", "cpu_status"], tools, outcomes)
    assert guard.review_required
    assert not guard.permits("workspace_write", tools["workspace_write"])
    assert guard.permits("cpu_status", tools["cpu_status"])


def test_failed_safe_read_and_preflight_denial_do_not_lock_effectful_voice():
    guard = VoiceRetryQuarantine()
    tools = {
        "cpu_status": {"function": lambda: "read",
                       "safety": {"effect": "read_only"}},
        "workspace_write": {"function": lambda: "write",
                            "safety": {"effect": "write"}},
    }
    guard.observe(["cpu_status"], tools, {
        "cpu_status": {"state": "failed", "attempted": True},
    })
    guard.observe(["workspace_write"], tools, {
        "workspace_write": {"state": "blocked", "attempted": False},
    })
    assert not guard.review_required
    assert guard.permits("workspace_write", tools["workspace_write"])


def test_stop_after_successful_write_but_before_llm_also_latches(
        tmp_path, monkeypatch):
    stop, calls = [False], []
    core = create_core(
        tmp_path, monkeypatch,
        {"workspace_write": {"function": lambda: calls.append(1) or "OK",
                              "safety": {"effect": "write"}}},
        lambda _: plan("workspace_write"),
        on_chat=lambda: stop.__setitem__(0, True),
    )
    verify = verifier_for(stop)
    first = core.respond_voice("write", plan_verifier=verify)
    assert calls == [1]
    assert first["tool_execution_status"] == "completed"
    assert first["tool_dispatch_blocked"] is True
    assert first["manual_reconciliation_required"] is True
    stop[0] = False
    repeat = core.respond_voice("write again", plan_verifier=verify)
    assert calls == [1]
    assert repeat["tool_dispatch_blocked"]


def test_typed_text_remains_independent_of_voice_quarantine(
        tmp_path, monkeypatch):
    calls = []
    core = create_core(
        tmp_path, monkeypatch,
        {"workspace_write": {"function": lambda: calls.append("ran") or "OK",
                              "safety": {"effect": "write"}}},
        lambda _: plan("workspace_write"),
    )
    core._voice_retry_quarantine.observe(
        ["workspace_write"], core.tools,
        {"workspace_write": {"state": "unknown", "attempted": True}},
    )
    response = core.respond("typed")
    assert response["tool_results"]["workspace_write"] == "OK"
    assert calls == ["ran"]


def test_tool_exception_after_cancel_is_unknown_not_failed():
    stop, effects, details = [False], [], {}
    def fail_after_stop():
        effects.append("effect")
        stop[0] = True
        raise RuntimeError("SECRET_DO_NOT_REPORT")
    result = run_tools(
        ["workspace_write", "cpu_status"],
        {
            "workspace_write": {"function": fail_after_stop},
            "cpu_status": {"function": lambda: effects.append("never")},
        },
        execution_guard=lambda *_: True,
        execution_cancelled=lambda: stop[0],
        outcome_details=details,
    )
    assert effects == ["effect"]
    assert result["workspace_write"] == EXECUTION_INTERRUPTED_MESSAGE
    assert result["cpu_status"] == EXECUTION_BLOCKED_MESSAGE
    assert details["workspace_write"] == {"state": "unknown", "attempted": True}
    assert "SECRET" not in str(result)
