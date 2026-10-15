"""Offline camera tool status regression. Fake result data only; no devices."""
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
from core.tool_outcome import classify_guarded_result, summarize_guarded_outcomes
from core.voice_pipeline import classify_tool_plan_risk
from core.voice_plan_attestation import (
    allow_voice_dispatch,
    sign_voice_plan,
    same_voice_plan,
)
from modules.camera import capture, video, video_frames, stream


CAMERA_MODULES = (
    (capture, "camera_capture", "Kamerabilden kunde inte tas:"),
    (video, "camera_record_video", "Videoinspelningen misslyckades:"),
    (video_frames, "camera_sample_video_frames",
     "Bildrutor kunde inte plockas ut ur videon:"),
    (stream, "camera_stream_status", "Kamerastream-testet misslyckades:"),
)


@pytest.mark.parametrize("module,name,prefix", CAMERA_MODULES)
def test_camera_registry_is_explicitly_sensitive_with_failure_contract(
        module, name, prefix):
    tool = module.TOOLS[name]
    assert tool["safety"]["voice_confirmation_required"] is True
    assert tool["safety"]["effect"] != "read_only"
    assert prefix in tool["result_failure_prefixes"]
    plan = {"steps": [{"tool": name, "input": "synthetic"}]}
    assert classify_tool_plan_risk(plan, {name: tool})["level"] == "high"
    assert allow_voice_dispatch(
        plan, {name: tool}, name, tool, None,
        plan_verifier=lambda *_: False,
    ) is False


@pytest.mark.parametrize("module,name,prefix", CAMERA_MODULES)
def test_camera_reported_failure_ends_guarded_plan_without_late_write(
        monkeypatch, module, name, prefix):
    called = []
    errors = {
        "success": False, "error": "SYNTHETIC_PRIVATE_ERROR",
        "disabled": False,
    }
    if module is capture:
        monkeypatch.setattr(capture, "capture_from_settings", lambda: errors)
    elif module is video:
        monkeypatch.setattr(video, "record_video_from_settings", lambda: errors)
    elif module is video_frames:
        monkeypatch.setattr(
            video_frames, "sample_latest_video_from_settings", lambda: errors
        )
    else:
        monkeypatch.setattr(stream, "run_bounded_stream", lambda: errors)

    tools = {
        name: module.TOOLS[name],
        "workspace_write": {
            "function": lambda: called.append("write"),
            "safety": {"effect": "write"},
        },
    }
    details = {}
    results = run_tools(
        [name, "workspace_write"], tools,
        execution_guard=lambda *_: True,
        outcome_details=details,
    )
    assert called == []
    assert results[name] == EXECUTION_FAILED_MESSAGE
    assert results["workspace_write"] == EXECUTION_BLOCKED_MESSAGE
    assert details[name] == {"state": "failed", "attempted": True}
    assert details["workspace_write"] == {
        "state": "blocked", "attempted": False
    }
    assert summarize_guarded_outcomes(details) == "failed"
    assert "SYNTHETIC_PRIVATE_ERROR" not in str(results)
    assert "SYNTHETIC_PRIVATE_ERROR" not in str(details)


def test_disabled_stream_is_reported_as_failed_not_completed(monkeypatch):
    monkeypatch.setattr(
        stream, "run_bounded_stream",
        lambda: {"success": False, "disabled": True, "error": "OFF"},
    )
    report = stream.camera_stream_status()
    assert report.startswith("Kamerastream är avstängd.")
    assert classify_guarded_result(
        report, stream.TOOLS["camera_stream_status"]
    ) == (False, None)


@pytest.mark.parametrize("module,name,prefix", CAMERA_MODULES)
def test_positive_camera_format_is_not_misclassified_as_failure(
        module, name, prefix):
    if module is capture:
        success = capture.format_capture_result({
            "success": True, "path": "synthetic.jpg",
            "width": 20, "height": 10,
        })
    elif module is video:
        success = video.format_video_result({
            "success": True, "path": "synthetic.mp4",
            "width": 20, "height": 10, "frames": 8, "fps": 4.0,
        })
    elif module is video_frames:
        success = video_frames.format_video_frame_result({
            "success": True, "frames": [],
            "video_path": "synthetic.mp4", "total_frames": 8,
        })
    else:
        success = stream.format_stream_result({
            "success": True, "frames": 8, "fps": 4.0,
            "camera_index": 0, "width": 20, "height": 10,
        })
    assert classify_guarded_result(
        success, module.TOOLS[name]
    ) == (True, success)


def test_camera_policy_change_invalidates_voice_attestation():
    registry = {"camera_capture": deepcopy(capture.TOOLS["camera_capture"])}
    plan = {"steps": [{"tool": "camera_capture", "input": "synthetic"}]}
    secret = secrets.token_bytes(32)
    digest = sign_voice_plan(plan, registry, secret)
    assert same_voice_plan(plan, registry, secret, digest)
    registry["camera_capture"]["result_failure_prefixes"] = ()
    assert not same_voice_plan(plan, registry, secret, digest)


def test_camera_failure_plus_prior_success_is_partially_completed(monkeypatch):
    monkeypatch.setattr(
        capture, "capture_from_settings",
        lambda: {"success": False, "error": "PRIVATE_CAMERA_ERROR"},
    )
    tools = {
        "cpu_status": {"function": lambda: "synthetic status OK"},
        "camera_capture": capture.TOOLS["camera_capture"],
    }
    details = {}
    result = run_tools(
        ["cpu_status", "camera_capture"], tools,
        execution_guard=lambda *_: True,
        outcome_details=details,
    )
    assert result["cpu_status"] == "synthetic status OK"
    assert result["camera_capture"] == EXECUTION_FAILED_MESSAGE
    assert summarize_guarded_outcomes(details) == "partially_completed"


class FakeMemory:
    def search(self, *_): return []
    def format(self, *_): return "none"


class FakeLLM:
    def __init__(self): self.calls = []
    def chat(self, *args, **kwargs):
        self.calls.append("chat")
        return "synthetic response"


def test_myai_core_camera_failure_never_asks_llm_to_report_success(
        tmp_path, monkeypatch):
    import core.assistant as assistant_module
    monkeypatch.setattr(
        capture, "capture_from_settings",
        lambda: {"success": False, "error": "PRIVATE_CAMERA_DETAILS"},
    )
    calls = []
    tools = {
        "camera_capture": capture.TOOLS["camera_capture"],
        "workspace_write": {
            "function": lambda: calls.append("write"),
            "safety": {"effect": "write"},
        },
    }
    plan = {"steps": [
        {"tool": "camera_capture", "input": "synthetic capture"},
        {"tool": "workspace_write", "input": "synthetic write"},
    ]}
    monkeypatch.setattr(
        assistant_module, "select_tool_plan",
        lambda *_args, **_kwargs: deepcopy(plan),
    )
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"]["auto_assess_enabled"] = False
    llm = FakeLLM()
    core = MyAICore(
        settings, tmp_path, tools=tools, memory=FakeMemory(), llm=llm,
    )
    secret = secrets.token_bytes(32)
    digest = sign_voice_plan(plan, core.tools, secret)
    result = core.respond_voice(
        "synthetic camera voice",
        plan_verifier=lambda p, t: same_voice_plan(p, t, secret, digest),
    )
    assert calls == []
    assert llm.calls == []
    assert result["tool_execution_status"] == "failed"
    assert result["tool_outcomes"]["camera_capture"]["attempted"] is True
    assert result["tool_outcomes"]["workspace_write"]["attempted"] is False
    assert "PRIVATE_CAMERA_DETAILS" not in str(result)
    assert result["tool_dispatch_blocked"] is True


def test_unguarded_camera_error_keeps_original_readable_text(monkeypatch):
    monkeypatch.setattr(
        capture, "capture_from_settings",
        lambda: {"success": False, "error": "syntetiskt testfel"},
    )
    got = run_tools(
        ["camera_capture"], capture.TOOLS,
    )
    assert got["camera_capture"] == (
        "Kamerabilden kunde inte tas: syntetiskt testfel"
    )
