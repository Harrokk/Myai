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
    assert settings["camera"]["stream_enabled"] is False
    assert settings["camera"]["stream_duration_seconds"] == 5
    assert settings["camera"]["stream_fps"] == 2
    assert settings["camera"]["stream_max_frames"] == 10
    assert settings["vision"]["enabled"] is False
    assert settings["vision"]["model"] == ""
    assert settings["vision"]["timeout_seconds"] == 120
    assert settings["location"]["enabled"] is False
    assert settings["location"]["source"] == "gps_serial"
    assert settings["location"]["serial_port"] == ""
    assert settings["location"]["baudrate"] == 9600
    assert settings["location"]["max_lines"] == 20
    assert settings["research"]["candidate_limit"] == 5
    assert settings["research"]["top_n"] == 3
    assert settings["research"]["min_source_reliability"] == 40
    assert settings["research"]["min_information_confidence"] == 40
    assert settings["research"]["weights"]["relevance"] == 0.30
    assert settings["research"]["weights"]["practicality"] == 0.10
    assert settings["internet"]["enabled"] is False
    assert settings["internet"]["provider"] == "searxng"
    assert settings["internet"]["searxng_url"] == "http://localhost:8080"
    assert settings["internet"]["max_results"] == 5
    assert settings["internet"]["safesearch"] == 1
