"""Operator-verified Alma V1 can be selected without weakening older pins.

Source-only, fake sparse ONNX files. No model import, microphone, speaker,
network, LLM, training or runtime App Lab process is exercised here.
"""
import hashlib
import json

import pytest

from modules.voice import piper_alma_provider as provider


def _model(tmp_path):
    file = tmp_path / "sv_SE-alma-medium.onnx"
    with file.open("wb") as handle:
        handle.truncate(60_000_000)  # sparse fixture, no model weights
    with file.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return file, digest


def _compact_sidecar(model, *, rate=22050):
    config = {
        "audio": {"sample_rate": rate},
        "espeak": {"voice": "sv"},
        "num_speakers": 1,
        "phoneme_id_map": {"ɧ": [72], "ɕ": [55]},
    }
    sidecar = model.with_name(model.name + ".json")
    sidecar.write_text(
        json.dumps(config, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    with sidecar.open("rb") as handle:
        sha = hashlib.file_digest(handle, "sha256").hexdigest()
    return sidecar, sha


def _fake_operator_pin(monkeypatch, model, *, config_sha):
    with model.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    sidecar = model.with_name(model.name + ".json")
    monkeypatch.setattr(provider, "_OPERATOR_ALMA_SHA256", digest)
    monkeypatch.setattr(provider, "_OPERATOR_ALMA_SIZE", model.stat().st_size)
    monkeypatch.setattr(provider, "_OPERATOR_ALMA_SIDECAR_SHA256", config_sha)
    monkeypatch.setattr(
        provider, "_OPERATOR_ALMA_SIDECAR_SIZE", sidecar.stat().st_size,
    )


def test_verified_operator_hashes_match_exact_source_contract():
    assert provider._OPERATOR_ALMA_SHA256 == \
        "b4bfecd22e30cf28f514eeea06c0da440be1721435a652d0571ee65963ce8f65"
    assert provider._OPERATOR_ALMA_SIDECAR_SHA256 == \
        "f7467e5d2ada0239004fca552f42b25ac90a92b848e5c283aec13a1f26a85f84"
    assert provider._OPERATOR_ALMA_SIZE == 63434611
    assert provider._OPERATOR_ALMA_SIDECAR_SIZE == 3907
    assert provider._ALMA_SHA256 != provider._OPERATOR_ALMA_SHA256


def test_exact_paired_operator_model_allowed(monkeypatch, tmp_path):
    model, _ = _model(tmp_path)
    sidecar, digest = _compact_sidecar(model)
    _fake_operator_pin(monkeypatch, model, config_sha=digest)
    tts = provider.PiperAlmaTTS(voice_id=str(model))
    assert tts._verified_voice_path() == model
    assert tts._voice is None


def test_tampered_sidecar_fails_even_when_json_still_valid(monkeypatch, tmp_path):
    model, _ = _model(tmp_path)
    sidecar, digest = _compact_sidecar(model)
    _fake_operator_pin(monkeypatch, model, config_sha=digest)
    cfg = json.loads(sidecar.read_text(encoding="utf-8"))
    cfg["espeak"]["voice"] = "en"
    sidecar.write_text(json.dumps(cfg, ensure_ascii=False, sort_keys=True),
                       encoding="utf-8")
    with pytest.raises(RuntimeError, match="integrity"):
        provider.PiperAlmaTTS(voice_id=str(model))._verified_voice_path()


def test_bad_model_hash_not_accepted(monkeypatch, tmp_path):
    model, _ = _model(tmp_path)
    _, digest = _compact_sidecar(model)
    _fake_operator_pin(monkeypatch, model, config_sha=digest)
    with model.open("r+b") as handle:
        handle.seek(120)
        handle.write(b"bad")
    with pytest.raises(RuntimeError, match="integrity"):
        provider.PiperAlmaTTS(voice_id=str(model))._verified_voice_path()


def test_invalid_audio_format_fails_even_if_sidecar_is_pinned(monkeypatch, tmp_path):
    model, _ = _model(tmp_path)
    sidecar, digest = _compact_sidecar(model, rate=16000)
    _fake_operator_pin(monkeypatch, model, config_sha=digest)
    with pytest.raises(RuntimeError, match="integrity"):
        provider.PiperAlmaTTS(voice_id=str(model))._verified_voice_path()


def test_prior_legacy_pin_still_accepts_original_metadata(monkeypatch, tmp_path):
    model, digest = _model(tmp_path)
    monkeypatch.setattr(provider, "_ALMA_SHA256", digest)
    sidecar = model.with_name(model.name + ".json")
    config = {
        "dataset": "alma", "language": {"code": "sv_SE"},
        "audio": {"sample_rate": 22050}, "espeak": {"voice": "sv"},
        "annotation": "X" * 4100,
    }
    sidecar.write_text(json.dumps(config), encoding="utf-8")
    assert provider.PiperAlmaTTS(voice_id=str(model))._verified_voice_path() == model


def test_legacy_variant_rejects_invalid_metadata(monkeypatch, tmp_path):
    model, digest = _model(tmp_path)
    monkeypatch.setattr(provider, "_ALMA_SHA256", digest)
    sidecar = model.with_name(model.name + ".json")
    config = {
        "dataset": "alma", "language": {"code": "en_US"},
        "audio": {"sample_rate": 22050}, "espeak": {"voice": "sv"},
        "annotation": "X" * 4100,
    }
    sidecar.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(RuntimeError, match="integrity"):
        provider.PiperAlmaTTS(voice_id=str(model))._verified_voice_path()


def test_sidecar_symlink_is_never_accepted(monkeypatch, tmp_path):
    model, _ = _model(tmp_path)
    sidecar, digest = _compact_sidecar(model)
    _fake_operator_pin(monkeypatch, model, config_sha=digest)
    moved = tmp_path / "model-config.json"
    sidecar.rename(moved)
    sidecar.symlink_to(moved)
    with pytest.raises(RuntimeError, match="missing or incomplete"):
        provider.PiperAlmaTTS(voice_id=str(model))._verified_voice_path()
