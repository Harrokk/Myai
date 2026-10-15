"""No physical device, audio, LLM inference or actual write operations."""
from copy import deepcopy
import secrets

import pytest

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.tool_manager import run_tools
from core.voice_pipeline import VoicePipeline
from core.voice_plan_attestation import (
    allow_voice_dispatch,
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
        return "syntetiskt testsvar"
    def chat_stream(self, *_args, **_kwargs):
        self.calls.append("chat_stream")
        return iter(["syntetiskt ", "testsvar"])


class FakeRecognizer:
    def __init__(self, text):
        self.text = text
    def transcribe(self, _audio):
        return {"text": self.text, "confidence": 0.99}


class Clock:
    def __init__(self):
        self.now = 1.0
    def __call__(self):
        return self.now


WRITE = 'Skapa filen "notes.txt" med innehållet Hej.'
READ = "Hur mycket CPU används?"


def make_core(tmp_path):
    effects = []
    tools = {
        "workspace_write": {
            "function": lambda text: effects.append(("write", text)),
            "pass_user_input": True,
            "safety": {"effect": "write", "voice_confirmation_required": True},
        },
        "cpu_status": {
            "function": lambda: effects.append(("read",)) or "CPU OK",
        },
    }
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"]["auto_assess_enabled"] = False
    return MyAICore(
        settings, tmp_path, tools=tools, memory=Memory(), llm=LLM(),
    ), effects


def test_tool_manager_blocks_guarded_tool_at_actual_invocation():
    invoked = []
    tools = {"workspace_write": {
        "function": lambda text: invoked.append(text),
        "pass_user_input": True,
        "safety": {"effect": "write"},
    }}
    result = run_tools(
        ["workspace_write"], tools, user_input=WRITE,
        execution_guard=lambda *_: False,
    )
    assert invoked == []
    assert "blockerades" in result["workspace_write"]


def test_execution_guard_exception_fails_closed_without_exposing_secret():
    invoked = []
    tools = {"workspace_write": {
        "function": lambda text: invoked.append(text),
        "pass_user_input": True,
    }}
    def broken(*_args):
        raise RuntimeError("SECRET_PASSWORD_FROM_GUARD")
    result = run_tools(
        ["workspace_write"], tools, user_input=WRITE,
        execution_guard=broken,
    )
    assert not invoked
    assert "SECRET_PASSWORD" not in str(result)
    assert "blockerades" in result["workspace_write"]


def test_unconfirmed_voice_write_blocked_but_typed_text_still_works(tmp_path):
    core, effects = make_core(tmp_path)
    denied = core.respond_voice(
        WRITE, plan_verifier=lambda *_: False,
    )
    assert effects == []
    assert "blockerades" in denied["tool_results"]["workspace_write"]
    assert denied["tool_dispatch_blocked"] is True
    assert denied["answer"].startswith("Verktygsåtgärden stoppades")
    assert core.llm.calls == []
    result = core.respond(WRITE)
    assert effects == [("write", WRITE)]
    assert "blockerades" not in str(result["tool_results"])


def test_voice_safe_read_still_works_without_approval(tmp_path):
    core, effects = make_core(tmp_path)
    result = core.respond_voice(
        READ, plan_verifier=lambda *_: False,
    )
    assert result["tool_results"]["cpu_status"] == "CPU OK"
    assert effects == [("read",)]


def test_unmarked_effectful_memory_action_is_never_implicit_voice_read():
    calls = []
    tools = {"memory_review_action": {
        "function": lambda text: calls.append(text),
        "pass_user_input": True,
    }}
    plan = {"steps": [{
        "tool": "memory_review_action",
        "input": "GODKÄNN MINNESGRANSKNING 1",
    }]}
    assert allow_voice_dispatch(
        plan, tools, "memory_review_action", tools["memory_review_action"],
        "GODKÄNN MINNESGRANSKNING 1", lambda *_: False,
    ) is False
    assert calls == []


def test_changed_tool_argument_after_speech_preview_is_denied(tmp_path, monkeypatch):
    import core.assistant as module
    core, effects = make_core(tmp_path)
    secret = secrets.token_bytes(32)
    previous = core.preview_tool_plan(WRITE)
    digest = sign_voice_plan(previous, core.tools, secret)
    actual = module.select_tool_plan
    def swapped(*args, **kwargs):
        plan = actual(*args, **kwargs)
        if plan["steps"]:
            plan["steps"][0]["input"] = (
                'Skapa filen "OTHER.txt" med innehållet Hej.'
            )
        return plan
    monkeypatch.setattr(module, "select_tool_plan", swapped)
    result = core.respond_voice(
        WRITE, plan_verifier=lambda plan, tools: same_voice_plan(
            plan, tools, secret, digest
        ),
    )
    assert effects == []
    assert "blockerades" in result["tool_results"]["workspace_write"]
    assert core.llm.calls == []


def test_modified_callable_after_speech_preview_is_denied(tmp_path):
    core, effects = make_core(tmp_path)
    key = secrets.token_bytes(32)
    plan = core.preview_tool_plan(WRITE)
    digest = sign_voice_plan(plan, core.tools, key)
    core.tools["workspace_write"]["function"] = (
        lambda text: effects.append(("injected", text))
    )
    result = core.respond_voice(
        WRITE,
        plan_verifier=lambda p, t: same_voice_plan(p, t, key, digest),
    )
    assert not effects
    assert "blockerades" in result["tool_results"]["workspace_write"]


def test_modified_tool_safety_after_preview_is_denied(tmp_path):
    core, effects = make_core(tmp_path)
    key = secrets.token_bytes(32)
    plan = core.preview_tool_plan(WRITE)
    digest = sign_voice_plan(plan, core.tools, key)
    core.tools["workspace_write"]["safety"]["effect"] = "destructive"
    result = core.respond_voice(
        WRITE,
        plan_verifier=lambda p, t: same_voice_plan(p, t, key, digest),
    )
    assert not effects
    assert "blockerades" in result["tool_results"]["workspace_write"]


def test_invalid_plan_cannot_generate_voice_authorization():
    key = secrets.token_bytes(32)
    with pytest.raises(ValueError):
        sign_voice_plan(
            {"steps": [{"tool": "x", "input": object()}]},
            {"x": {"function": lambda: None}},
            key,
        )


def test_approved_voice_plan_allows_exact_single_write(tmp_path):
    core, effects = make_core(tmp_path)
    key = secrets.token_bytes(32)
    plan = core.preview_tool_plan(WRITE)
    digest = sign_voice_plan(plan, core.tools, key)
    result = core.respond_voice(
        WRITE,
        plan_verifier=lambda p, t: same_voice_plan(p, t, key, digest),
    )
    assert effects == [("write", WRITE)]
    assert result["tool_results"]["workspace_write"] is None


def test_unapproved_voice_stream_write_is_blocked(tmp_path):
    core, effects = make_core(tmp_path)
    result = core.respond_voice_stream(
        WRITE, plan_verifier=lambda *_: False,
    )
    assert effects == []
    assert "blockerades" in result["tool_results"]["workspace_write"]
    assert result["streamed"] is False
    assert result["tool_dispatch_blocked"] is True
    assert core.llm.calls == []


def test_spoken_intermediate_confirmation_cannot_bypass_dispatch(tmp_path, monkeypatch):
    core, effects = make_core(tmp_path)
    monkeypatch.setattr(
        core.intermediate_results, "parse_confirmation",
        lambda _: 7,
    )
    result = core.respond_voice(
        "BEKRÄFTA FORSKNING 7",
        plan_verifier=lambda *_: True,
    )
    assert effects == []
    assert result["tools"] == []
    assert "röst" in result["tool_results"]["intermediate_protocol"]


def test_real_voice_pipeline_integration_requires_confirmed_hmac(tmp_path):
    core, effects = make_core(tmp_path)
    clock = Clock()
    a = FakeRecognizer(WRITE)
    backups = [FakeRecognizer(WRITE), FakeRecognizer(WRITE)]
    config = deepcopy(DEFAULT_SETTINGS)
    config["voice"].update({
        "high_risk_confirmation_enabled": True,
        "redundancy_enabled": True,
        "redundant_transcript_count": 3,
    })
    pipeline = VoicePipeline(
        core, a, backup_stt=backups,
        settings=config, clock=clock,
    )
    initial = pipeline.process_utterance(b"fake-audio")
    assert initial["status"] == "confirmation_required"
    assert effects == []
    a.text = "bekräfta"
    for backup in backups:
        backup.text = "bekräfta"
    result = pipeline.process_utterance(b"fake-audio")
    assert result["status"] == "completed"
    assert effects == [("write", WRITE)]
    assert result["assistant"]["tool_results"]["workspace_write"] is None


def test_read_only_tool_with_mutated_write_effect_not_allowed(tmp_path):
    core, effects = make_core(tmp_path)
    core.tools["cpu_status"]["safety"] = {"effect": "write"}
    result = core.respond_voice(
        READ, plan_verifier=lambda *_: False,
    )
    assert effects == []
    assert "blockerades" in result["tool_results"]["cpu_status"]



def test_unconfirmed_dangerous_voice_never_claims_completed(tmp_path):
    core, effects = make_core(tmp_path)
    recognizer = FakeRecognizer(WRITE)
    backup1 = FakeRecognizer(WRITE)
    backup2 = FakeRecognizer(WRITE)
    cfg = deepcopy(DEFAULT_SETTINGS)
    cfg["memory"]["auto_assess_enabled"] = False
    cfg["voice"]["high_risk_confirmation_enabled"] = False
    pipeline = VoicePipeline(
        core, recognizer,
        backup_stt=[backup1, backup2],
        settings=cfg, clock=Clock(),
    )
    result = pipeline.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert result["assistant"]["tool_dispatch_blocked"] is True
    assert "stoppades" in result["message"]
    assert effects == []
    assert core.llm.calls == []
