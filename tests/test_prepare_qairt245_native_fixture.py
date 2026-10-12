"""Deterministic QNN scale-offset UFXP8 fixture safety tests."""
import hashlib
import json

import pytest

import scripts.prepare_qairt245_native_fixture as mod


def test_quantized_input_is_exact_64_bytes_and_round_trips():
    raw = mod.native_input()
    assert isinstance(raw, bytes)
    assert len(raw) == 64
    assert min(raw) == 122
    assert max(raw) == 134
    assert raw[6] == 128
    for q, source in zip(raw, mod.input_values()):
        assert abs(mod.decode_ufxp8(q) - source) <= 1e-7


def test_qnn_scale_offset_sign_convention():
    assert mod.encode_ufxp8(0) == 128
    assert mod.decode_ufxp8(128) == 0
    assert mod.encode_ufxp8(-6 / 32) == 122
    assert mod.encode_ufxp8(6 / 32) == 134
    assert mod.decode_ufxp8(0) == -4
    assert mod.decode_ufxp8(255) == 3.96875


def test_invalid_quantization_params_rejected():
    for value in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            mod.encode_ufxp8(value)
    with pytest.raises(ValueError):
        mod.encode_ufxp8(0, scale=0)
    with pytest.raises(ValueError):
        mod.decode_ufxp8(256)


def test_native_fixture_refuses_arm_even_when_onnx_missing(tmp_path):
    with pytest.raises(RuntimeError, match="host-only"):
        mod.produce_native_fixture(
            tmp_path / "input", tmp_path / "output", machine="aarch64",
        )


def test_unverified_onnx_does_not_write(tmp_path):
    dest = tmp_path / "output"
    with pytest.raises(ValueError, match="unverified-host-onnx"):
        mod.produce_native_fixture(tmp_path / "missing", dest, machine="x86_64")
    assert not dest.exists()


def test_verified_fixture_written_only_to_new_temp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "verified_fixture_presence", lambda _: True)
    out = tmp_path / "native"
    report = mod.produce_native_fixture(tmp_path, out, machine="x86_64")
    content = (out / "input_native_u8.raw").read_bytes()
    assert content == mod.native_input()
    assert report["native_input_bytes"] == 64
    assert report["native_input_sha256"] == hashlib.sha256(content).hexdigest()
    assert report["exact_float32_roundtrip_verified"] is True
    assert report["qnn_cpu_result_matched"] is False
    assert report["htp_context_created"] is False
    assert report["htp_execution_measured"] is False
    assert report["live_services_changed"] is False
    assert (out / "input_list_native.txt").read_text() == "input_native_u8.raw\n"
    assert json.loads((out / "native_fixture_metadata.json").read_text()) == report
    with pytest.raises(ValueError, match="already-exists"):
        mod.produce_native_fixture(tmp_path, out, machine="x86_64")


def test_no_dlc_digest_no_native_input(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "verified_fixture_presence", lambda _: True)
    monkeypatch.setattr(mod, "MODEL_SHA", "0" * 64)
    with pytest.raises(ValueError, match="unverified-synthetic-dlc"):
        mod.produce_native_fixture(tmp_path, tmp_path / "out", machine="x86_64")
    assert not (tmp_path / "out").exists()


def test_output_64_byte_count_is_not_htp_profiling():
    assert mod.OUTPUT_SCALE == 1 / 512
    assert mod.OUTPUT_QNN_OFFSET == 0
    assert len(mod.native_input()) == 64
