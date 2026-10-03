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
    assert settings["voice"]["enabled"] is False
    assert settings["voice"]["tts_enabled"] is False
    assert settings["voice"]["redundancy_enabled"] is True
    assert settings["voice"]["primary_confidence_threshold"] == 0.72
    assert settings["voice"]["consensus_similarity_threshold"] == 0.62
    assert settings["voice"]["redundant_transcript_count"] == 3
    assert settings["voice"]["vad_start_speech_frames"] == 2
    assert settings["voice"]["vad_end_silence_frames"] == 3
    assert settings["voice"]["vad_max_frames"] == 500
    assert settings["voice"]["microphone_provider"] == "sounddevice"
    assert settings["voice"]["vad_provider"] == "webrtcvad"
    assert settings["voice"]["stt_provider"] == "faster_whisper"
    assert settings["voice"]["tts_provider"] == "pyttsx3"
    assert settings["voice"]["sample_rate"] == 16000
    assert settings["voice"]["channels"] == 1
    assert settings["voice"]["sample_width"] == 2
    assert settings["voice"]["frame_ms"] == 20
    assert settings["voice"]["backup_stt_models"] == []
    assert settings["voice"]["tts_rate"] == 180
    assert settings["voice"]["tts_async"] is True
    assert settings["voice"]["tts_stop_timeout_seconds"] == 2.0
    assert settings["voice"]["session_max_wait_frames"] == 1500
    assert settings["voice"]["handsfree_enabled"] is False
    assert settings["voice"]["handsfree_max_wait_frames"] == 1500
    assert settings["voice"]["handsfree_stop_timeout_seconds"] == 3.0
    assert settings["voice"]["echo_guard_enabled"] is True
    assert settings["voice"]["echo_guard_window_seconds"] == 5.0
    assert settings["voice"]["echo_guard_similarity_threshold"] == 0.78
    assert settings["voice"]["echo_guard_min_words"] == 3
    assert settings["voice"]["echo_guard_for_high_risk"] is False
    assert settings["voice"]["semantic_consensus_enabled"] is False
    assert settings["voice"]["semantic_consensus_for_high_risk"] is False
    assert settings["voice"]["semantic_consensus_min_confidence"] == 0.85
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
    assert settings["research"]["conflict_penalty"] == 10.0
    assert settings["research"]["conflict_relative_tolerance"] == 0.05
    assert settings["shopping"]["top_results"] == 3
    assert settings["shopping"]["min_seller_reliability"] == 50.0
    assert settings["shopping"]["max_offers"] == 20
    assert settings["shopping"]["candidate_pages"] == 5
    assert settings["shopping"]["fx_provider"] == "frankfurter"
    assert settings["shopping"]["frankfurter_url"] == "https://api.frankfurter.app"
    assert settings["shopping"]["fx_timeout_seconds"] == 10
    assert settings["research"]["weights"]["relevance"] == 0.40
    assert settings["research"]["weights"]["source_reliability"] == 0.35
    assert settings["research"]["weights"]["information_confidence"] == 0.25
