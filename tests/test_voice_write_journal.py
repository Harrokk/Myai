"""Disposable-file crash/restart tests for guarded voice write marker only."""
from copy import deepcopy
from pathlib import Path
import os
import subprocess
import sys

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.tool_manager import EXECUTION_BLOCKED_MESSAGE
from core.voice_write_journal import VoiceWriteAheadMarker, MARKER, BODY


class Memory:
    def search(self, *_args):
        return []
    def format(self, *_args):
        return "none"


class LLM:
    def __init__(self):
        self.calls = 0
    def chat(self, *_args, **_kwargs):
        self.calls += 1
        return "synthetic text"


def create_core(root, monkeypatch, tools, selected):
    import core.assistant as assistant_module
    config = deepcopy(DEFAULT_SETTINGS)
    config["memory"]["auto_assess_enabled"] = False
    core = MyAICore(config, root, tools=tools, memory=Memory(), llm=LLM())
    monkeypatch.setattr(
        assistant_module, "select_tool_plan",
        lambda *_args, **_kwargs: {
            "source": "synthetic",
            "steps": [{"tool": selected(), "input": "synthetic only"}],
        },
    )
    return core


def verifier():
    def approved(*_args):
        return True
    approved.voice_stop_requested = lambda: False
    return approved


def test_durable_marker_created_before_callback_and_survives_new_core(
        tmp_path, monkeypatch):
    calls = []
    selected = ["workspace_write"]
    def writer():
        marker = VoiceWriteAheadMarker(tmp_path)
        assert marker.review_required is True
        calls.append("write")
        return "SUCCESS"
    def reader():
        calls.append("read")
        return "CPU OK"
    tools = {
        "workspace_write": {
            "function": writer,
            "safety": {"effect": "write", "voice_confirmation_required": True},
        },
        "cpu_status": {"function": reader, "safety": {"effect": "read_only"}},
    }
    first_core = create_core(tmp_path, monkeypatch, tools, lambda: selected[0])
    first = first_core.respond_voice("synthetic", plan_verifier=verifier())
    assert first["tool_execution_status"] == "completed"
    assert calls == ["write"]
    marker_file = tmp_path / "runtime" / MARKER
    assert marker_file.read_bytes() == BODY
    assert marker_file.stat().st_mode & 0o777 == 0o600

    # Distinct core models a process restart with lost in-memory lock.
    new_core = create_core(tmp_path, monkeypatch, tools, lambda: selected[0])
    blocked = new_core.respond_voice("synthetic", plan_verifier=verifier())
    assert blocked["tool_execution_status"] == "not_started"
    assert blocked["tool_results"]["workspace_write"] == EXECUTION_BLOCKED_MESSAGE
    assert blocked["tool_dispatch_blocked"] is True
    assert blocked["manual_reconciliation_required"] is True
    assert calls == ["write"]
    selected[0] = "cpu_status"
    read = new_core.respond_voice("read status", plan_verifier=verifier())
    assert read["tool_execution_status"] == "completed"
    assert read["tool_results"]["cpu_status"] == "CPU OK"
    assert calls == ["write", "read"]


def test_crash_before_tool_result_retains_pending_marker(tmp_path):
    source = (
        "import os,sys\n"
        "from core.voice_write_journal import VoiceWriteAheadMarker\n"
        "j=VoiceWriteAheadMarker(sys.argv[1])\n"
        "assert j.begin_effect() is True\n"
        "os._exit(0)\n"
    )
    child = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False, timeout=8,
    )
    assert child.returncode == 0
    assert VoiceWriteAheadMarker(tmp_path).review_required
    assert VoiceWriteAheadMarker(tmp_path).begin_effect() is False


def test_exclusive_marker_protects_separate_instances_and_repeat(tmp_path):
    a, b = VoiceWriteAheadMarker(tmp_path), VoiceWriteAheadMarker(tmp_path)
    assert a.begin_effect() is True
    assert b.begin_effect() is False
    assert a.begin_effect() is False
    assert (tmp_path / "runtime" / MARKER).read_bytes() == BODY


def test_unwritable_or_untrusted_runtime_denies_voice_writes(tmp_path):
    (tmp_path / "runtime").symlink_to(tmp_path / "another")
    journal = VoiceWriteAheadMarker(tmp_path)
    assert journal.begin_effect() is False
    assert journal.review_required
    assert not (tmp_path / "another" / MARKER).exists()


def test_preexisting_symlink_marker_denied_without_following(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    sentinel = tmp_path / "other-file"
    sentinel.write_text("PRIVATE_SENTINEL", encoding="utf-8")
    (runtime / MARKER).symlink_to(sentinel)
    journal = VoiceWriteAheadMarker(tmp_path)
    assert journal.review_required
    assert journal.begin_effect() is False
    assert sentinel.read_text(encoding="utf-8") == "PRIVATE_SENTINEL"


def test_writing_marker_failure_fails_closed(monkeypatch, tmp_path):
    original = os.fsync
    def fail_fsync(fd):
        raise OSError("SYNTHETIC_PRIVATE_IO_ERROR")
    monkeypatch.setattr(os, "fsync", fail_fsync)
    journal = VoiceWriteAheadMarker(tmp_path)
    assert journal.begin_effect() is False
    assert journal.review_required
    monkeypatch.setattr(os, "fsync", original)
    assert VoiceWriteAheadMarker(tmp_path).begin_effect() is False


def test_guarded_before_call_failure_does_not_invoke_tool():
    from core.tool_manager import run_tools
    effects, details = [], {}
    result = run_tools(
        ["workspace_write"],
        {"workspace_write": {"function": lambda: effects.append("NOT_RUN")}},
        execution_guard=lambda *_: True,
        execution_before_call=lambda *_: False,
        outcome_details=details,
    )
    assert effects == []
    assert result == {"workspace_write": EXECUTION_BLOCKED_MESSAGE}
    assert details["workspace_write"] == {"state": "blocked", "attempted": False}


def test_typed_text_does_not_create_voice_marker(tmp_path, monkeypatch):
    calls = []
    tools = {"workspace_write": {"function": lambda: calls.append(1) or "DONE",
                                  "safety": {"effect": "write"}}}
    core = create_core(tmp_path, monkeypatch, tools, lambda: "workspace_write")
    result = core.respond("synthetic typed command")
    assert result["tool_results"]["workspace_write"] == "DONE"
    assert calls == [1]
    assert not (tmp_path / "runtime" / MARKER).exists()
