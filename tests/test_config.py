import json

from core.config import DEFAULT_SETTINGS, load_settings


def test_load_settings_uses_defaults_when_file_is_missing(tmp_path):
    settings = load_settings(tmp_path / "missing.json")

    assert settings["ollama"]["model"] == DEFAULT_SETTINGS["ollama"]["model"]
    assert settings["memory"]["database"] == "memory.db"


def test_load_settings_merges_partial_override(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"ollama": {"model": "test-model"}}),
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings["ollama"]["model"] == "test-model"
    assert settings["ollama"]["url"] == DEFAULT_SETTINGS["ollama"]["url"]
    assert settings["assistant"]["name"] == DEFAULT_SETTINGS["assistant"]["name"]
    assert settings["conversation"]["max_turns"] == 6
    assert settings["hardware_watch"]["enabled"] is True
    assert settings["hardware_watch"]["interval_seconds"] == 10
    assert settings["trusted_terminals"]["enabled"] is False
    assert settings["trusted_terminals"]["connect_rssi"] == -60
    assert settings["trusted_terminals"]["disconnect_rssi"] == -75
    assert settings["camera"]["default_index"] == 0
    assert settings["camera"]["capture_dir"] == "runtime/captures"
    assert settings["camera"]["video_dir"] == "runtime/video"
    assert settings["camera"]["video_duration_seconds"] == 5
    assert settings["camera"]["video_fps"] == 10
    assert settings["camera"]["video_frame_dir"] == "runtime/video_frames"
    assert settings["camera"]["video_sample_count"] == 5
    assert settings["location"]["enabled"] is False
    assert settings["location"]["file"] == "runtime/location.json"
    assert settings["location"]["max_age_seconds"] == 300
    assert settings["gps"]["enabled"] is False
    assert settings["gps"]["port"] == ""
    assert settings["gps"]["baudrate"] == 9600
    assert settings["gps"]["timeout_seconds"] == 10
    assert settings["files"]["enabled"] is True
    assert settings["files"]["workspace_root"] == "runtime/workspace"
    assert settings["files"]["write_enabled"] is False
    assert settings["files"]["max_read_chars"] == 20000
    assert settings["files"]["max_list_entries"] == 100
    assert ".txt" in settings["files"]["allowed_write_extensions"]
    assert settings["excel"]["enabled"] is True
    assert settings["excel"]["write_enabled"] is False
    assert settings["excel"]["max_rows_read"] == 100
    assert settings["excel"]["default_sheet"] == "Data"
    assert settings["vision"]["enabled"] is False
    assert settings["vision"]["model"] == ""
    assert settings["vision"]["timeout_seconds"] == 120
