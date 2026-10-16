"""Remote synthetic STT -> VoicePipeline -> dummy assistant -> WAV test."""
import json

from scripts import ventuno_remote_synthetic_e2e as flow


def test_fixed_synthetic_chain_checks_true_interface_without_hw():
    result = flow.run_contract()
    assert result["status"] == "synthetic-stt-llm-tts-fake-chain-verified"
    assert result["normal_voice_pipeline_with_fakes"] is True
    assert result["silence_rejected"] is True
    assert result["peak_python_allocations_under_32mib"] is True
    assert result["real_native_abi_verified"] is False
    assert result["physical_consent_implied"] is False
    assert result["no_microphone_or_speaker"] is True
    assert result["no_database_created"] is True


def test_fake_renderer_that_throws_cannot_be_marked_success(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic test fails")
    monkeypatch.setattr(flow, "run_synthetic_voice_chain", fail)
    report = flow.run_contract()
    assert report["status"] == "synthetic-contract-exception"
    assert report["normal_voice_pipeline_with_fakes"] is False


def test_status_does_not_log_text_audio_tokens_or_paths(capsys):
    assert flow.main() == 0
    body = capsys.readouterr().out
    report = json.loads(body.partition("=")[2])
    assert "MyAI" not in body
    assert "runtime/" not in body
    assert "hej" not in body.lower()
    assert report["no_geniex_or_ollama"] is True
