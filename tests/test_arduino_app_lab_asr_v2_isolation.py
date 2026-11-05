"""Enforce source-tree and event isolation for the new Arduino ASR track.

No Arduino SDK, USB, Whisper models or real microphone are imported.
"""
import ast
import json
from pathlib import Path

import pytest

from integrations.arduino_app_lab.asr_v2.boundary import (
    TRACK_ID, FinalTextOneShotGate, check_disabled_track_config,
)

ROOT = Path(__file__).resolve().parents[1]
TRACK = ROOT / "integrations/arduino_app_lab/asr_v2"
POLICY = TRACK / "track.json"


def test_only_disabled_new_track_is_accepted():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["track"] == TRACK_ID
    assert check_disabled_track_config(policy) is True
    for key in (
        "enabled", "legacy_pcm_whisper_enabled",
        "microphone_capture_enabled", "local_model_queries_enabled",
        "tool_dispatch_enabled", "service_control_enabled",
    ):
        assert policy[key] is False


@pytest.mark.parametrize("key,override", [
    ("enabled", True),
    ("legacy_pcm_whisper_enabled", True),
    ("microphone_capture_enabled", True),
    ("local_model_queries_enabled", True),
    ("tool_dispatch_enabled", True),
    ("service_control_enabled", True),
    ("track", "legacy_pcm_whisper"),
    ("mode", "production"),
    ("schema_version", True),
])
def test_fail_closed_if_any_backend_could_be_enabled(key, override):
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy[key] = override
    with pytest.raises(ValueError):
        check_disabled_track_config(policy)


def test_no_unknown_config_keys_or_missing_policy():
    config = json.loads(POLICY.read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        check_disabled_track_config({**config, "execute": True})
    config.pop("enabled")
    with pytest.raises(ValueError):
        check_disabled_track_config(config)
    with pytest.raises(ValueError):
        check_disabled_track_config(None)


def test_only_first_final_text_is_consumed_and_never_reprinted():
    gate = FinalTextOneShotGate()
    assert gate.consume("full_text", "hemlig mening") is None
    assert gate.arm_once(explicit_ui_action=False) is False
    assert gate.arm_once(explicit_ui_action=True) is True
    assert gate.consume("partial_text", "hemlig mening") is None
    final = gate.consume("full_text", "  Vad heter du?  ")
    assert final is not None
    assert final.text == "Vad heter du?"
    assert "Vad" not in repr(final)
    assert gate.consume("full_text", "andra meningen") is None
    assert gate.arm_once(explicit_ui_action=True) is False


@pytest.mark.parametrize("words", [
    "", " ", "x" * 241, "hej\u0000", "hej\u200b",
    "Vänta en sekund säg Vad heter du",
])
def test_invalid_final_consumes_its_one_shot(words):
    gate = FinalTextOneShotGate()
    assert gate.arm_once(explicit_ui_action=True)
    assert gate.consume("full_text", words) is None
    assert gate.consume("full_text", "Vad heter du?") is None


def test_cancel_is_permanent_within_session():
    gate = FinalTextOneShotGate()
    assert gate.arm_once(explicit_ui_action=True)
    gate.cancel()
    assert gate.consume("full_text", "Vad heter du?") is None
    assert gate.arm_once(explicit_ui_action=True) is False


def test_new_adapter_cannot_import_old_voice_pipeline_or_device_apis():
    forbidden_modules = (
        "core", "modules", "scripts", "arduino", "sounddevice",
        "pyaudio", "numpy", "faster_whisper", "whisper",
        "subprocess", "importlib", "requests", "httpx", "os",
        "socket", "pathlib",
    )
    for source in sorted(TRACK.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    assert not name.name.startswith(forbidden_modules), source
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                assert not name.startswith(forbidden_modules), source
            elif isinstance(node, (ast.Call, ast.Attribute)):
                # Block common ways of importing/executing arbitrary code.
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id not in {"eval", "exec", "__import__"}, source


def test_production_voice_still_off_and_legacy_source_unchanged():
    config = json.loads((
        ROOT / "config/profiles/ventuno_q.json"
    ).read_text(encoding="utf-8"))
    assert config["voice"]["enabled"] is False
    assert config["voice"]["tts_enabled"] is False
    assert config["voice"]["handsfree_enabled"] is False
    assert (ROOT / "scripts/ventuno_usb_dialogue_hardware.py").is_file()
    assert (ROOT / "scripts/ventuno_app_lab_readonly_asr_bridge.py").is_file()
    assert (ROOT / "integrations/arduino_app_lab/myai_sv_asr_once").is_dir()
