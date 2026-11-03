"""Offline contract tests for privacy-safe Swedish TTS→VAD→ASR rate matrix.

All data/model objects are synthetic; no microphone, real model, network,
speaker, audio file, or decoded transcript output is permitted.
"""
import json

import pytest

import scripts.hosted_piper_silero_parakeet_triad as matrix


@pytest.mark.parametrize("expected,observed,band", [
    ("Vad heter du?", "VAD HETER DU!", "0"),
    ("Vad är temperaturen?", "Vad ar temperaturen?", "1-2"),
    ("Hej", "hej", "0"),
])
def test_distance_bands_are_bounded(expected, observed, band):
    got = matrix._distance_band(expected, observed)
    assert got == band


def test_distance_band_with_long_untrusted_output_is_not_emitted():
    assert matrix._distance_band("hej", "text" * 100) == "invalid"
    assert matrix._distance_band("hej", "") in ("1-2", "3-5")


def test_mocked_rate_matrix_is_source_only_and_sanitized(monkeypatch, tmp_path):
    calls = []
    class FakePiper:
        def __init__(self, *, voice_id, rate):
            assert voice_id
            self.rate = rate
        def _verified_voice_path(self):
            return True
        def render_wav(self, phrase):
            assert phrase in matrix.PHRASES
            calls.append((self.rate, phrase))
            return b"fake-wave"
        def release_for_inference(self):
            return True

    class FakeParakeet:
        def __init__(self, *, model_name):
            assert model_name
            self.transcribes = 0
        def _load_model(self):
            return True
        def transcribe(self, pcm):
            assert len(pcm) <= matrix.MAX_CAPTURE_BYTES + 32_000
            idx = self.transcribes // (1 + len(matrix.CONTEXTS_MS))
            self.transcribes += 1
            phrase = matrix.PHRASES[idx % len(matrix.PHRASES)]
            return {"text": phrase}
        def release_for_inference(self):
            return True

    seeds = []
    monkeypatch.setattr(matrix, "_set_synthesis_seed", seeds.append)
    monkeypatch.setattr(matrix, "verified_silero_model", lambda _: True)
    monkeypatch.setattr(matrix, "PiperAlmaTTS", FakePiper)
    monkeypatch.setattr(matrix, "SherpaOnnxParakeetSTT", FakeParakeet)
    monkeypatch.setattr(matrix, "_wav_to_16k_pcm", lambda _: bytes(640))
    monkeypatch.setattr(matrix, "public_pcm_vad_segments",
                        lambda pcm, path, **kwargs: [bytes(640)])
    out = matrix.benchmark(
        tmp_path / "fake-parakeet", tmp_path / "fake-vad.onnx",
        tmp_path / "fake-alma.onnx",
    )
    assert out["status"] == "hosted-synthetic-rate-matrix-quality-inconclusive"
    assert out["phrase_count"] == 3
    assert out["rate_count"] == 3
    assert out["scenario_count"] == 27
    assert out["functional_smoke_passed"] is True
    assert out["deployment_quality_certified"] is False
    assert out["seed_repeat_identical_count"] == 9
    assert all(row["seed_repeat_identical"] for row in out["results"])
    assert out["silero_exact_count"] == 27
    assert out["baseline_180_silero_exact_count"] == 3
    assert {r["rate"] for r in out["results"]} == {150, 180, 210}
    assert {r["context_padding_ms"] for r in out["results"]} == {0, 300, 500}
    assert all(r["silero_distance_band"] == "0" for r in out["results"])
    assert out["speaker_opened"] is False
    assert out["microphone_opened"] is False
    assert out["audio_saved"] is False
    assert len(calls) == 18
    assert len(seeds) == 18
    assert all(seeds[i] == seeds[i + 1] for i in range(0, len(seeds), 2))
    exposed = json.dumps(out, ensure_ascii=False)
    for phrase in matrix.PHRASES:
        assert phrase not in exposed


def test_wrong_silero_checksum_fails_before_any_native_load(monkeypatch, tmp_path):
    monkeypatch.setattr(matrix, "verified_silero_model", lambda _: False)
    monkeypatch.setattr(matrix, "PiperAlmaTTS",
                        lambda **kw: pytest.fail("never construct Piper"))
    with pytest.raises(RuntimeError, match="checksum rejected"):
        matrix.benchmark(tmp_path, tmp_path / "bad-vad.onnx", tmp_path)
