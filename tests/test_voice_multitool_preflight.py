"""Synthetic voice multi-tool authorization: no real actions or device access."""
from copy import deepcopy
import secrets

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.tool_manager import (
    EXECUTION_BLOCKED_MESSAGE,
    EXECUTION_FAILED_MESSAGE,
    EXECUTION_INTERRUPTED_MESSAGE,
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
    assert result["one"] == "Fel vid körning av one (feltext dold)."
    assert "historiskt testfel" not in str(result)
    assert result["two"] == "TWO"
    assert calls == ["two"]


def test_voice_stop_inside_active_tool_marks_attempted_unknown_and_blocks_next():
    """No text result or implicit rollback claim survives an in-flight Stop."""
    effects, outcomes = [], {}
    stop = [False]

    def first():
        effects.append("called")
        stop[0] = True
        return "SECRET_SUCCESS_LOOKING_RETURN"

    tools = {
        "cpu_status": {"function": first},
        "ram_status": {"function": lambda: effects.append("must_not_run")},
    }
    result = run_tools(
        ["cpu_status", "ram_status"], tools,
        execution_guard=lambda *_: True,
        execution_cancelled=lambda: stop[0],
        outcome_details=outcomes,
    )
    assert effects == ["called"]
    assert result == {
        "cpu_status": EXECUTION_INTERRUPTED_MESSAGE,
        "ram_status": EXECUTION_BLOCKED_MESSAGE,
    }
    assert outcomes["cpu_status"] == {"state": "unknown", "attempted": True}
    assert outcomes["ram_status"] == {"state": "blocked", "attempted": False}
    assert "SECRET" not in str(result)


def test_known_prior_voice_step_is_partial_when_later_step_stopped_mid_call():
    from core.tool_outcome import summarize_guarded_outcomes

    effects, outcomes = [], {}
    stop = [False]
    def finish():
        effects.append("read")
        return "read-value"
    def stop_in_second():
        effects.append("write_started")
        stop[0] = True
        return "unsafe_success_claim"
    tools = {
        "cpu_status": {"function": finish},
        "workspace_write": {"function": stop_in_second},
        "ram_status": {"function": lambda: effects.append("never")},
    }
    result = run_tools(
        ["cpu_status", "workspace_write", "ram_status"], tools,
        execution_guard=lambda *_: True,
        execution_cancelled=lambda: stop[0],
        outcome_details=outcomes,
    )
    assert effects == ["read", "write_started"]
    assert result["cpu_status"] == "read-value"
    assert result["workspace_write"] == EXECUTION_INTERRUPTED_MESSAGE
    assert result["ram_status"] == EXECUTION_BLOCKED_MESSAGE
    assert summarize_guarded_outcomes(outcomes) == "partially_completed"


def test_cancel_between_guard_and_invocation_starts_no_tool():
    effects, outcome = [], {}
    stop = [False]
    checks = [0]
    def guard(*_):
        checks[0] += 1
        if checks[0] == 2:
            stop[0] = True
        return True

    results = run_tools(
        ["cpu_status"],
        {"cpu_status": {"function": lambda: effects.append("no")}},
        execution_guard=guard,
        execution_cancelled=lambda: stop[0],
        outcome_details=outcome,
    )
    assert checks == [2]
    assert effects == []
    assert results["cpu_status"] == EXECUTION_BLOCKED_MESSAGE
    assert outcome["cpu_status"] == {"state": "blocked", "attempted": False}


def test_faulty_stop_probe_fails_closed_without_invocation():
    observed = []
    def invalid_probe():
        raise RuntimeError("SECRET_EVENT_FAILURE")
    results = run_tools(
        ["cpu_status"],
        {"cpu_status": {"function": lambda: observed.append("run")}},
        execution_guard=lambda *_: True,
        execution_cancelled=invalid_probe,
    )
    assert observed == []
    assert results["cpu_status"] == EXECUTION_BLOCKED_MESSAGE
    assert "SECRET" not in str(results)


def test_voice_core_stop_mid_tool_cannot_claim_full_completion(tmp_path, monkeypatch):
    """Integration: guarded tools, core status, memory and LLM stay truthful."""
    from core.tool_outcome import summarize_guarded_outcomes

    stop, effects = [False], []
    tools = {}
    def inflight():
        effects.append("already_started")
        stop[0] = True
        return "FALSE_SUCCESS"
    tools["cpu_status"] = {"function": inflight}
    plan = {"steps": [{"tool": "cpu_status", "input": "synthetic"}]}
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)
    def verifier(*_args):
        return True
    verifier.voice_stop_requested = lambda: stop[0]
    result = core.respond_voice("synthetic", plan_verifier=verifier)
    assert effects == ["already_started"]
    assert stop[0] is True
    assert result["tool_results"]["cpu_status"] == EXECUTION_INTERRUPTED_MESSAGE
    assert result["tool_outcomes"]["cpu_status"] == {
        "state": "unknown", "attempted": True,
    }
    assert summarize_guarded_outcomes(result["tool_outcomes"]) == "unknown"
    assert result["tool_execution_status"] == "unknown"
    assert result["manual_reconciliation_required"] is True
    assert result["tool_dispatch_blocked"] is True
    assert core.llm.calls == []
    assert core.conversation_history == []


def test_typed_text_tool_return_keeps_legacy_output_without_guard():
    effects = []
    result = run_tools(
        ["cpu_status"],
        {"cpu_status": {"function": lambda: effects.append(1) or "OK"}},
        execution_cancelled=lambda: True,
    )
    assert effects == [1]
    assert result == {"cpu_status": "OK"}


def test_cooperative_voice_tool_receives_live_cancel_probe_and_blocks_followups():
    """Opted-in tools can return promptly after Stop without false success."""
    from core.tool_outcome import ToolOutcome
    calls, detail = [], {}
    stopped = [False]

    def long_running(*, cancel_requested):
        assert callable(cancel_requested)
        calls.append("running")
        stopped[0] = True
        assert cancel_requested() is True
        calls.append("stopped_cooperatively")
        return ToolOutcome(False, "MAY_HAVE_WRITTEN_PRIVATE_DATA")

    tools = {
        "workspace_write": {
            "function": long_running,
            "safety": {"effect": "write", "voice_cancel_callback": True},
        },
        "cpu_status": {"function": lambda: calls.append("unexpected")},
    }
    result = run_tools(
        ["workspace_write", "cpu_status"], tools,
        execution_guard=lambda *_: True,
        execution_cancelled=lambda: stopped[0],
        outcome_details=detail,
    )
    assert calls == ["running", "stopped_cooperatively"]
    assert result["workspace_write"] == EXECUTION_INTERRUPTED_MESSAGE
    assert result["cpu_status"] == EXECUTION_BLOCKED_MESSAGE
    assert detail["workspace_write"] == {"state": "unknown", "attempted": True}
    assert "PRIVATE_DATA" not in str(result)


def test_cooperative_voice_tool_normal_success_passes_keyword_only_probe():
    calls = []
    def read_status(*, cancel_requested):
        calls.append(cancel_requested())
        return "CPU OK"
    result = run_tools(
        ["cpu_status"],
        {"cpu_status": {
            "function": read_status,
            "safety": {"effect": "read_only", "voice_cancel_callback": True},
        }},
        execution_guard=lambda *_: True,
        execution_cancelled=lambda: False,
    )
    assert result == {"cpu_status": "CPU OK"}
    assert calls == [False]


def test_cooperative_voice_tool_with_user_input_gets_both_arguments():
    received = []
    def action(query, *, cancel_requested):
        received.append((query, cancel_requested()))
        return "done"
    result = run_tools(
        ["workspace_write"],
        {"workspace_write": {
            "function": action, "pass_user_input": True,
            "safety": {"effect": "write", "voice_cancel_callback": True},
        }},
        user_input="synthetic request",
        execution_guard=lambda *_: True,
        execution_cancelled=lambda: False,
    )
    assert received == [("synthetic request", False)]
    assert result["workspace_write"] == "done"


def test_invalid_cooperative_signature_denies_entire_batch_before_actions():
    for bad in [
        lambda: "not cancellable",
        lambda cancel_requested: "not keyword-only",
    ]:
        effects = []
        tools = {
            "cpu_status": {"function": lambda: effects.append("read")},
            "workspace_write": {
                "function": bad,
                "safety": {"effect": "write", "voice_cancel_callback": True},
            },
        }
        res = run_tools(
            ["cpu_status", "workspace_write"], tools,
            execution_guard=lambda *_: True,
            execution_cancelled=lambda: False,
        )
        assert effects == []
        assert all(v == EXECUTION_BLOCKED_MESSAGE for v in res.values())


def test_cooperative_optin_missing_or_malformed_stop_probe_denies_without_call():
    effects = []
    tools = {"workspace_write": {
        "function": lambda *, cancel_requested: effects.append("called"),
        "safety": {"effect": "write", "voice_cancel_callback": True},
    }}
    for stop in (None, True, "not_a_callable"):
        res = run_tools(
            ["workspace_write"], tools,
            execution_guard=lambda *_: True,
            execution_cancelled=stop,
        )
        assert res["workspace_write"] == EXECUTION_BLOCKED_MESSAGE
    assert effects == []


def test_cooperative_safety_flag_mutation_invalidates_voice_hmac():
    from core.voice_plan_attestation import sign_voice_plan, same_voice_plan
    def action(*, cancel_requested):
        return "no write"
    tools = {"workspace_write": {
        "function": action,
        "safety": {"effect": "write", "voice_cancel_callback": True},
    }}
    plan = {"steps": [{"tool": "workspace_write", "input": "synthetic"}]}
    key = secrets.token_bytes(32)
    digest = sign_voice_plan(plan, tools, key)
    assert same_voice_plan(plan, tools, key, digest)
    tools["workspace_write"]["safety"]["voice_cancel_callback"] = False
    assert not same_voice_plan(plan, tools, key, digest)


def test_no_cooperative_keyword_is_passed_to_typical_existing_tool():
    effects = []
    def ordinary(value):
        effects.append(value)
        return "legacy tool okay"
    result = run_tools(
        ["workspace_write"],
        {"workspace_write": {
            "function": ordinary, "pass_user_input": True,
            "safety": {"effect": "write"},
        }},
        user_input="synthetic",
        execution_guard=lambda *_: True,
        execution_cancelled=lambda: False,
    )
    assert effects == ["synthetic"]
    assert result["workspace_write"] == "legacy tool okay"


def test_core_cooperative_voice_tool_requires_real_stop_hook(tmp_path, monkeypatch):
    calls = []
    def operation(*, cancel_requested):
        calls.append("unwanted")
        return "done"
    tools = {"workspace_write": {
        "function": operation,
        "safety": {"effect": "write", "voice_cancel_callback": True},
    }}
    plan = {"steps": [{"tool": "workspace_write", "input": "synthetic"}]}
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)

    # A bare verifier can approve a plan, but cannot actually supply
    # live cancellation for a callback claiming cooperative safety.
    result = core.respond_voice("synthetic", plan_verifier=lambda *_: True)
    assert calls == []
    assert result["tool_dispatch_blocked"] is True
    assert result["tool_results"]["workspace_write"] == EXECUTION_BLOCKED_MESSAGE
    assert core.llm.calls == []


def test_core_cooperative_voice_tool_works_with_real_stop_hook(tmp_path, monkeypatch):
    calls = []
    def operation(*, cancel_requested):
        calls.append(cancel_requested())
        return "done"
    tools = {"workspace_write": {
        "function": operation,
        "safety": {"effect": "write", "voice_cancel_callback": True},
    }}
    plan = {"steps": [{"tool": "workspace_write", "input": "synthetic"}]}
    core = core_with_plan(tmp_path, monkeypatch, tools, plan)

    def verifier(*_):
        return True
    verifier.voice_stop_requested = lambda: False
    result = core.respond_voice("synthetic", plan_verifier=verifier)
    assert calls == [False]
    assert result["tool_execution_status"] == "completed"
    # A durable marker remains even after success: the next effectful
    # voice action needs out-of-band state reconciliation.
    assert result["manual_reconciliation_required"] is True
