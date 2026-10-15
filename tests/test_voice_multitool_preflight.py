"""Synthetic voice multi-tool authorization: no real actions or device access."""
from copy import deepcopy
import secrets

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.tool_manager import (
    EXECUTION_BLOCKED_MESSAGE,
    run_tools,
)
from core.voice_plan_attestation import (
    same_voice_plan,
    sign_voice_plan,
)


class Memory:
    def search(self, *_args):
        return []
    def format(self, *_args):
        return "none"


class LLM:
    def __init__(self):
        self.calls = []
    def chat(self, *_args, **_kwargs):
        self.calls.append("chat")
        return "syntetiskt svar"
    def chat_stream(self, *_args, **_kwargs):
        self.calls.append("stream")
        return iter(["syntetiskt svar"])


def core_with_plan(tmp_path, monkeypatch, tool_registry, plan):
    import core.assistant as assistant_module
    config = deepcopy(DEFAULT_SETTINGS)
    config["memory"]["auto_assess_enabled"] = False
    core = MyAICore(
        config, tmp_path, tools=tool_registry,
        llm=LLM(), memory=Memory(),
    )
    monkeypatch.setattr(
        assistant_module, "select_tool_plan",
        lambda *_args, **_kwargs: deepcopy(plan),
    )
    return core


def test_guarded_preflight_denies_all_when_later_write_is_unapproved():
    calls = []
    tools = {
        "cpu_status": {
            "function": lambda: calls.append("read") or "OK",
        },
        "workspace_write": {
            "function": lambda value: calls.append(("write", value)),
            "pass_user_input": True,
            "safety": {"effect": "write"},
        },
    }
    result = run_tools(
        ["cpu_status", "workspace_write"], tools,
        user_input="Skapa fil", execution_guard=lambda name, *_: (
            name == "cpu_status"
        ),
    )
    assert calls == []
    assert result == {
        "cpu_status": EXECUTION_BLOCKED_MESSAGE,
        "workspace_write": EXECUTION_BLOCKED_MESSAGE,
    }


def test_guarded_duplicate_names_are_not_dispatched():
    calls = []
    result = run_tools(
        ["cpu_status", "cpu_status"],
        {"cpu_status": {"function": lambda: calls.append("read")}},
        execution_guard=lambda *_: True,
    )
    assert calls == []
    assert result == {"cpu_status": EXECUTION_BLOCKED_MESSAGE}


def test_guarded_invalid_last_step_blocks_earlier_valid_step():
    calls = []
    result = run_tools(
        ["cpu_status", "unregistered"],
        {"cpu_status": {"function": lambda: calls.append("read")}},
        execution_guard=lambda *_: True,
    )
    assert calls == []
    assert all(x == EXECUTION_BLOCKED_MESSAGE for x in result.values())


def test_guarded_invalid_or_missing_later_input_blocks_all():
    calls = []
    tools = {
        "cpu_status": {"function": lambda: calls.append("read")},
        "workspace_write": {
            "function": lambda arg: calls.append(arg),
            "pass_user_input": True,
        },
    }
    result = run_tools(
        ["cpu_status", "workspace_write"], tools,
        execution_guard=lambda *_: True,
    )
    assert calls == []
    assert all(v == EXECUTION_BLOCKED_MESSAGE for v in result.values())


def test_guarded_batch_over_16_is_denied_before_any_side_effect():
    calls = []
    tools = {
        f"read_{i}": {"function": lambda: calls.append("read")}
        for i in range(17)
    }
    result = run_tools(
        list(tools), tools, execution_guard=lambda *_: True,
    )
    assert calls == []
    assert len(result) == 17
    assert set(result.values()) == {EXECUTION_BLOCKED_MESSAGE}


def test_guarded_read_then_failed_tool_blocks_later_mutation():
    calls = []
    def broken(_value):
        calls.append("fails")
        raise RuntimeError("SECRET_PRIVATE_EXCEPTION_TEXT")
    tools = {
        "cpu_status": {
            "function": lambda: calls.append("read") or "CPU OK",
        },
        "workspace_write": {
            "function": broken, "pass_user_input": True,
            "safety": {"effect": "write"},
        },
        "ram_status": {
            "function": lambda: calls.append("unwanted read"),
        },
    }
    result = run_tools(
        ["cpu_status", "workspace_write", "ram_status"], tools,
        user_input="synthetic",
        execution_guard=lambda *_: True,
    )
    assert calls == ["read", "fails"]
    assert result["cpu_status"] == "CPU OK"
    assert result["workspace_write"] == EXECUTION_FAILED_MESSAGE
    assert result["ram_status"] == EXECUTION_BLOCKED_MESSAGE
    assert "SECRET_PRIVATE" not in str(result)


def test_guarded_last_step_exception_returns_denied_instead_of_success():
    calls = []
    def failed(_value):
        calls.append("tried")
        raise OSError("SECRET_MESSAGE")
    result = run_tools(
        ["workspace_write"],
        {"workspace_write": {
            "function": failed,
            "pass_user_input": True,
        }},
        user_input="synthetic",
        execution_guard=lambda *_: True,
    )
    assert calls == ["tried"]
    assert result["workspace_write"] == EXECUTION_FAILED_MESSAGE
    assert "SECRET" not in str(result)


def test_guarded_registry_mutation_after_first_step_blocks_next():
    calls = []
    tools = {}
    def first():
        calls.append("first")
        tools["workspace_write"]["safety"]["effect"] = "destructive"
        return "first OK"
    tools.update({
        "cpu_status": {"function": first},
        "workspace_write": {
            "function": lambda text: calls.append(("write", text)),
            "pass_user_input": True,
            "safety": {"effect": "write"},
        },
        "ram_status": {
            "function": lambda: calls.append("late"),
        },
    })
    plan = {"steps": [
        {"tool": "cpu_status", "input": "a"},
        {"tool": "workspace_write", "input": "b"},
        {"tool": "ram_status", "input": "c"},
    ]}
    key = secrets.token_bytes(32)
    digest = sign_voice_plan(plan, tools, key)
    result = run_tools(
        ["cpu_status", "workspace_write", "ram_status"], tools,
        tool_inputs={"workspace_write": "b"},
        execution_guard=lambda name, entry, value: same_voice_plan(
            plan, tools, key, digest
        ),
    )
    assert calls == ["first"]
    assert result["cpu_status"] == "first OK"
    assert result["workspace_write"] == EXECUTION_BLOCKED_MESSAGE
    assert result["ram_status"] == EXECUTION_BLOCKED_MESSAGE


def test_full_myai_multi_step_voice_denial_calls_no_tool_or_llm(
        tmp_path, monkeypatch):
    calls = []
    tools = {
        "cpu_status": {
            "function": lambda: calls.append("cpu"),
        },
        "workspace_write": {
            "function": lambda value: calls.append(("write", value)),
            "pass_user_input": True,
            "safety": {
                "effect": "write",
                "voice_confirmation_required": True,
            },
        },
    }
    plan = {"steps": [
        {"tool": "cpu_status", "input": "status"},
        {"tool": "workspace_write", "input": "do not execute"},
    ]}
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)
    result = core.respond_voice(
        "syntetisk multi-röstplan",
        plan_verifier=lambda *_: False,
    )
    assert calls == []
    assert result["tool_dispatch_blocked"] is True
    assert core.llm.calls == []
    assert result["answer"].startswith("Verktygsåtgärden stoppades")
    assert set(result["tool_results"].values()) == {
        EXECUTION_BLOCKED_MESSAGE
    }


def test_full_myai_multi_step_voice_approved_plan_can_execute(
        tmp_path, monkeypatch):
    calls = []
    tools = {
        "cpu_status": {
            "function": lambda: calls.append("cpu") or "OK",
        },
        "workspace_write": {
            "function": lambda value: calls.append(("write", value))
                        or "SKRIV TEST OK",
            "pass_user_input": True,
            "safety": {
                "effect": "write",
                "voice_confirmation_required": True,
            },
        },
    }
    plan = {"steps": [
        {"tool": "cpu_status", "input": "status"},
        {"tool": "workspace_write", "input": "synthetic test only"},
    ]}
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)
    key = secrets.token_bytes(32)
    digest = sign_voice_plan(plan, tools, key)
    result = core.respond_voice(
        "syntetisk multi-röstplan",
        plan_verifier=lambda plan, registry: same_voice_plan(
            plan, registry, key, digest
        ),
    )
    assert calls == ["cpu", ("write", "synthetic test only")]
    assert result["tool_dispatch_blocked"] is False
    assert result["tool_results"]["cpu_status"] == "OK"
    assert len(core.llm.calls) == 1


def test_guarded_partial_failure_prevents_llm_success_claim(
        tmp_path, monkeypatch):
    calls = []
    def broken(_text):
        calls.append("failed")
        raise RuntimeError("SECRET_BACKGROUND")
    tools = {
        "cpu_status": {
            "function": lambda: calls.append("read") or "OK",
        },
        "workspace_write": {
            "function": broken,
            "pass_user_input": True,
            "safety": {"effect": "write"},
        },
    }
    plan = {"steps": [
        {"tool": "cpu_status", "input": "some"},
        {"tool": "workspace_write", "input": "synthetic"},
    ]}
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)
    key = secrets.token_bytes(32)
    digest = sign_voice_plan(plan, tools, key)
    result = core.respond_voice_stream(
        "synthetic",
        plan_verifier=lambda p, t: same_voice_plan(p, t, key, digest),
    )
    assert calls == ["read", "failed"]
    assert result["tool_dispatch_blocked"] is True
    assert "SECRET" not in str(result)
    assert core.llm.calls == []
    assert result["streamed"] is False


def test_unguarded_text_execution_still_collects_other_tool_results():
    calls = []
    def fail():
        raise ValueError("historiskt testfel")
    result = run_tools(
        ["one", "two"],
        {
            "one": {"function": fail},
            "two": {"function": lambda: calls.append("two") or "TWO"},
        },
    )
    assert "historiskt testfel" in result["one"]
    assert result["two"] == "TWO"
    assert calls == ["two"]
