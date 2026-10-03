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
    assert settings["vision"]["enabled"] is False
    assert settings["vision"]["model"] == ""
    assert settings["vision"]["timeout_seconds"] == 120
    assert settings["gps"]["enabled"] is False
    assert settings["gps"]["port"] == ""
    assert settings["gps"]["baudrate"] == 9600
    assert settings["gps"]["max_lines"] == 20
    assert settings["internet"]["enabled"] is False
    assert settings["internet"]["provider"] == "searxng"
    assert settings["internet"]["searxng_url"] == ""
    assert settings["internet"]["max_results"] == 5
    assert settings["internet"]["max_page_bytes"] == 1_000_000
    assert settings["internet"]["max_page_chars"] == 20_000
    assert settings["internet"]["max_redirects"] == 5
    assert settings["research"]["candidate_limit"] == 5
    assert settings["research"]["top_results"] == 3
    assert settings["research"]["deep_verification_enabled"] is True
    assert settings["research"]["deep_blend"] == 0.40
    assert settings["research"]["weights"]["relevance"] == 0.40
    assert settings["research"]["weights"]["source_reliability"] == 0.35
    assert settings["research"]["weights"]["information_confidence"] == 0.25
    assert settings["shopping"]["top_results"] == 3
    assert settings["shopping"]["min_source_reliability"] == 50
    assert settings["voice"]["enabled"] is False
    assert settings["voice"]["stt_provider"] == ""
    assert settings["voice"]["tts_provider"] == ""
    assert settings["voice"]["speak_responses"] is True
    assert settings["voice"]["primary_confidence_threshold"] == 0.80
    assert settings["voice"]["high_risk_confidence_threshold"] == 0.90
    assert settings["voice"]["max_interpretations"] == 3
    assert settings["voice"]["redundant_for_high_risk"] is True
    assert settings["voice"]["vad_enabled"] is True
    assert settings["voice"]["vad_sample_rate"] == 16000
    assert settings["voice"]["vad_frame_ms"] == 20
    assert settings["voice"]["vad_rms_threshold"] == 500
    assert settings["voice"]["vad_start_frames"] == 2
    assert settings["voice"]["vad_end_silence_frames"] == 8
    assert settings["voice"]["vad_pre_roll_frames"] == 2
    assert settings["voice"]["max_utterance_seconds"] == 30
