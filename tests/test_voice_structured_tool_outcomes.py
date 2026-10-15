"""Synthetic guarded tool outcome statuses; no real files or device actions."""
from copy import deepcopy
import secrets

import pytest

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.tool_manager import (
    EXECUTION_BLOCKED_MESSAGE,
    EXECUTION_FAILED_MESSAGE,
    run_tools,
)
from core.tool_outcome import (
    ToolOutcome,
    classify_guarded_result,
    summarize_guarded_outcomes,
)
from core.voice_plan_attestation import same_voice_plan, sign_voice_plan


class Memory:
    def search(self, *_):
        return []

    def format(self, *_):
        return "inga minnen"


class LLM:
    def __init__(self):
        self.calls = []

    def chat(self, *_, **__):
        self.calls.append("chat")
        return "syntetiskt svar"

    def chat_stream(self, *_, **__):
        self.calls.append("chat_stream")
        yield "syntetiskt svar"


def core_with_plan(tmp_path, monkeypatch, tools, plan):
    import core.assistant as source
    config = deepcopy(DEFAULT_SETTINGS)
    config["memory"]["auto_assess_enabled"] = False
    core = MyAICore(
        config, tmp_path, tools=tools, llm=LLM(), memory=Memory(),
    )
    monkeypatch.setattr(
        source, "select_tool_plan",
        lambda *_args, **_kwargs: deepcopy(plan),
    )
    return core


def _plan(*steps):
    return {"steps": [
        {"tool": tool, "input": user_input}
        for tool, user_input in steps
    ]}


def _verified(core, plan):
    secret = secrets.token_bytes(32)
    approved = sign_voice_plan(plan, core.tools, secret)
    return lambda actual_plan, tools: same_voice_plan(
        actual_plan, tools, secret, approved,
    )


def test_explicit_failed_outcome_stops_all_later_steps():
    calls = []
    tools = {
        "cpu_status": {"function": lambda: calls.append("read") or "CPU OK"},
        "workspace_write": {
            "function": lambda _: calls.append("attempt") or ToolOutcome(
                success=False, value="SECRET_TEST_ERROR"
            ),
            "pass_user_input": True,
            "safety": {"effect": "write"},
        },
        "ram_status": {"function": lambda: calls.append("late")},
    }
    outcome = {}
    result = run_tools(
        list(tools), tools, user_input="synthetic",
        execution_guard=lambda *_: True, outcome_details=outcome,
    )
    assert calls == ["read", "attempt"]
    assert result == {
        "cpu_status": "CPU OK",
        "workspace_write": EXECUTION_FAILED_MESSAGE,
        "ram_status": EXECUTION_BLOCKED_MESSAGE,
    }
    assert outcome == {
        "cpu_status": {"state": "succeeded", "attempted": True},
        "workspace_write": {"state": "failed", "attempted": True},
        "ram_status": {"state": "blocked", "attempted": False},
    }
    assert summarize_guarded_outcomes(outcome) == "partially_completed"
    assert "SECRET_TEST_ERROR" not in str(result)
    assert "SECRET_TEST_ERROR" not in str(outcome)


def test_dict_success_false_is_explicit_failure_without_exception():
    calls = []
    tools = {
        "workspace_write": {
            "function": lambda _: {"success": False, "secret": "SECRET"},
            "pass_user_input": True,
        },
        "ram_status": {"function": lambda: calls.append("late")},
    }
    state = {}
    got = run_tools(
        list(tools), tools, user_input="x",
        execution_guard=lambda *_: True, outcome_details=state,
    )
    assert got["workspace_write"] == EXECUTION_FAILED_MESSAGE
    assert got["ram_status"] == EXECUTION_BLOCKED_MESSAGE
    assert calls == []
    assert summarize_guarded_outcomes(state) == "failed"
    assert "SECRET" not in str(got)


def test_opt_in_legacy_failure_prefix_blocks_without_exporting_error():
    calls = []
    tools = {
        "excel_append": {
            "function": lambda _: (
                "Kunde inte lägga till Excel-raden: "
                "SECRET_WORKBOOK_PATH.xlsx"
            ),
            "pass_user_input": True,
            "safety": {"effect": "write"},
            "result_failure_prefixes": (
                "Kunde inte lägga till Excel-raden:",
            ),
        },
        "workspace_write": {
            "function": lambda _: calls.append("unwanted"),
            "pass_user_input": True,
        },
    }
    state = {}
    got = run_tools(
        list(tools), tools, user_input="synthetic",
        execution_guard=lambda *_: True, outcome_details=state,
    )
    assert calls == []
    assert got["excel_append"] == EXECUTION_FAILED_MESSAGE
    assert got["workspace_write"] == EXECUTION_BLOCKED_MESSAGE
    assert state["excel_append"]["attempted"] is True
    assert state["workspace_write"]["attempted"] is False
    assert "SECRET_WORKBOOK_PATH" not in str(got)


def test_legacy_failure_prefix_matches_case_insensitively_only_at_start():
    meta = {"result_failure_prefixes": ("Kunde inte skapa Excel-filen:",)}
    assert classify_guarded_result(
        "KUnde inte Skapa excel-FILEN: SECRET", meta,
    ) == (False, None)
    value = "Data nämner: Kunde inte skapa Excel-filen: förklaringsrad"
    assert classify_guarded_result(value, meta) == (True, value)


def test_raw_legacy_unmarked_text_not_guessed_to_be_failure():
    value = "Kunde inte göra något."
    assert classify_guarded_result(value, {}) == (True, value)


def test_explicit_success_outcome_preserves_existing_visible_result():
    tools = {"cpu_status": {"function": lambda: ToolOutcome(True, "CPU OK")}}
    state = {}
    result = run_tools(
        ["cpu_status"], tools,
        execution_guard=lambda *_: True, outcome_details=state,
    )
    assert result == {"cpu_status": "CPU OK"}
    assert state == {
        "cpu_status": {"state": "succeeded", "attempted": True},
    }
    assert summarize_guarded_outcomes(state) == "completed"


def test_failed_only_step_is_failed_not_never_started():
    result_status = {}
    got = run_tools(
        ["workspace_write"],
        {"workspace_write": {
            "function": lambda: ToolOutcome(False, "SECRET"),
        }},
        execution_guard=lambda *_: True,
        outcome_details=result_status,
    )
    assert got["workspace_write"] == EXECUTION_FAILED_MESSAGE
    assert result_status["workspace_write"] == {
        "state": "failed", "attempted": True,
    }
    assert summarize_guarded_outcomes(result_status) == "failed"


def test_preflight_denial_reports_not_started_without_execution():
    calls = []
    names = ["cpu_status", "workspace_write"]
    tools = {
        "cpu_status": {"function": lambda: calls.append("read")},
        "workspace_write": {"function": lambda: calls.append("write")},
    }
    state = {}
    got = run_tools(
        names, tools, execution_guard=lambda name, *_: name == "cpu_status",
        outcome_details=state,
    )
    assert calls == []
    assert set(got.values()) == {EXECUTION_BLOCKED_MESSAGE}
    assert summarize_guarded_outcomes(state) == "not_started"
    assert all(x == {"state": "blocked", "attempted": False}
               for x in state.values())


def test_guard_failure_exception_keeps_sanitized_not_started():
    tools = {"workspace_write": {"function": lambda: pytest.fail("EXECUTED")}}
    state = {}
    def bad_guard(*_):
        raise RuntimeError("SECRET_EXCEPTION")
    got = run_tools(
        ["workspace_write"], tools, execution_guard=bad_guard,
        outcome_details=state,
    )
    assert got["workspace_write"] == EXECUTION_BLOCKED_MESSAGE
    assert summarize_guarded_outcomes(state) == "not_started"
    assert "SECRET_EXCEPTION" not in str(state)


def test_raised_exception_is_failed_and_never_claimed_not_attempted():
    def failed():
        raise RuntimeError("SECRET_RUNTIME_DETAILS")
    state = {}
    got = run_tools(
        ["cpu_status"], {"cpu_status": {"function": failed}},
        execution_guard=lambda *_: True, outcome_details=state,
    )
    assert got["cpu_status"] == EXECUTION_FAILED_MESSAGE
    assert state["cpu_status"] == {
        "state": "failed", "attempted": True,
    }
    assert "SECRET_RUNTIME" not in str(got)


def test_tool_outcome_invalid_success_value_is_rejected():
    with pytest.raises(TypeError):
        ToolOutcome(success="false")


def test_registry_known_text_failures_are_explicit_not_guesswork():
    from modules.files.workspace import TOOLS as file_tools
    from modules.files.excel import TOOLS as excel_tools
    from modules.system.memory_admin import TOOLS as memory_tools
    for registry, name, phrase in (
        (file_tools, "workspace_write", "Kunde inte skriva filen: SECRET"),
        (excel_tools, "excel_create", "Kunde inte skapa Excel-filen: SECRET"),
        (excel_tools, "excel_append",
         "Kunde inte lägga till Excel-raden: SECRET"),
        (excel_tools, "excel_set_cell",
         "Kunde inte ändra Excel-cellen: SECRET"),
        (excel_tools, "excel_create_sheet",
         "Kunde inte skapa Excel-bladet: SECRET"),
        (memory_tools, "memory_review_action",
         "Minnet kunde inte raderas: SECRET"),
    ):
        ok, payload = classify_guarded_result(phrase, registry[name])
        assert ok is False
        assert payload is None


def test_adapter_policy_change_invalidates_private_voice_hmac():
    tools = {"workspace_write": {
        "function": lambda _: "OK",
        "safety": {"effect": "write"},
        "result_failure_prefixes": ("Kunde inte:",),
    }}
    plan = _plan(("workspace_write", "synthetic"))
    key = secrets.token_bytes(32)
    digest = sign_voice_plan(plan, tools, key)
    assert same_voice_plan(plan, tools, key, digest) is True
    tools["workspace_write"]["result_failure_prefixes"] = ()
    assert same_voice_plan(plan, tools, key, digest) is False


def test_core_reports_partial_completion_with_no_llm_success_claim(tmp_path, monkeypatch):
    calls = []
    def failed(_):
        calls.append("attempt-write")
        return ToolOutcome(False, "SECRET_PRIVATE")
    tools = {
        "cpu_status": {"function": lambda: calls.append("read") or "OK"},
        "workspace_write": {
            "function": failed,
            "pass_user_input": True,
            "safety": {"effect": "write", "voice_confirmation_required": True},
        },
        "ram_status": {"function": lambda: calls.append("late")},
    }
    plan = _plan(("cpu_status", "read"), ("workspace_write", "write"),
                 ("ram_status", "read"))
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)
    answer = core.respond_voice(
        "syntetiskt kommando", plan_verifier=_verified(core, plan),
    )
    assert calls == ["read", "attempt-write"]
    assert answer["tool_dispatch_blocked"] is True
    assert answer["tool_execution_status"] == "partially_completed"
    assert answer["tool_outcomes"]["workspace_write"] == {
        "state": "failed", "attempted": True,
    }
    assert "Tidigare ändringar kan finnas kvar" in answer["answer"]
    assert core.llm.calls == []
    assert "SECRET_PRIVATE" not in str(answer)


def test_core_reports_not_started_for_rejected_batch(tmp_path, monkeypatch):
    calls = []
    tools = {
        "cpu_status": {"function": lambda: calls.append("read")},
        "workspace_write": {
            "function": lambda _: calls.append("write"),
            "pass_user_input": True,
            "safety": {"effect": "write"},
        },
    }
    plan = _plan(("cpu_status", "read"), ("workspace_write", "write"))
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)
    result = core.respond_voice(
        "syntetiskt", plan_verifier=lambda *_: False,
    )
    assert calls == []
    assert result["tool_execution_status"] == "not_started"
    assert result["tool_outcomes"]["cpu_status"]["attempted"] is False
    assert result["tool_dispatch_blocked"] is True


def test_core_success_status_preserved_for_approved_plan(tmp_path, monkeypatch):
    calls = []
    tools = {
        "cpu_status": {"function": lambda: calls.append("read") or "OK"},
    }
    plan = _plan(("cpu_status", "read"))
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)
    result = core.respond_voice(
        "syntetiskt", plan_verifier=_verified(core, plan),
    )
    assert calls == ["read"]
    assert result["tool_execution_status"] == "completed"
    assert result["tool_dispatch_blocked"] is False


def test_unguarded_text_api_retains_original_return_values():
    raw = {"success": False, "reason": "legacy result"}
    registry = {"workspace_write": {"function": lambda: raw}}
    assert run_tools(["workspace_write"], registry) == {
        "workspace_write": raw,
    }
    assert run_tools(
        ["workspace_write"],
        {"workspace_write": {
            "function": lambda: ToolOutcome(False, "old text response")
        }},
    ) == {"workspace_write": "old text response"}
