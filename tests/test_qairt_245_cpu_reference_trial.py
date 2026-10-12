"""Isolated CPU-only QNN DLC comparison safety and exact-file tests."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.qairt_245_cpu_reference_trial as mod


def test_cpu_cli_uses_only_cpu_backend_and_native_io(tmp_path):
    sdk = tmp_path / mod.SDK_VERSION
    args = mod.cpu_cli_arguments(sdk, tmp_path / "fixture.dlc",
                                 tmp_path / "list.txt", tmp_path / "outputs")
    assert "libQnnCpu.so" in " ".join(args)
    assert "libQnnModelDlc.so" in " ".join(args)
    assert "--dlc_path" in args
    assert "--use_native_input_files" in args
    assert "--use_native_output_files" in args
    assert "libQnnHtp.so" not in " ".join(args)


def test_missing_dlc_and_unrelated_model_refused(tmp_path):
    p = tmp_path / "unrelated.dlc"
    p.write_bytes(b"untrusted")
    assert mod.verify_dlc(p) is False
    assert mod.verify_dlc(tmp_path / "missing") is False


def test_native_input_matches_exact_verified_64_bytes(tmp_path):
    p = tmp_path / "native.raw"
    p.write_bytes(mod.native_input())
    assert mod.verify_native_file(p) is True
    p.write_bytes(b"\0" * 64)
    assert mod.verify_native_file(p) is False


def test_no_cpu_run_on_arm_device(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("unsafe backend load"))
    r = mod.trial(tmp_path, tmp_path, tmp_path, tmp_path, tmp_path / "out")
    assert r["status"] == "no-go"
    assert r["htp_executed"] is False
    assert r["ventuno_services_modified"] is False


def test_refuse_unverified_dlc_before_cpu_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod, "verified_fixture_presence", lambda _: True)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("unexpected process"))
    sdk = tmp_path / mod.SDK_VERSION
    sdk.mkdir()
    r = mod.trial(sdk, tmp_path / "wrong.dlc", tmp_path,
                  tmp_path, tmp_path / "out")
    assert r["status"] == "reject-dlc-digest"
    assert r["cpu_backend_loaded"] is False


def test_refuse_bad_native_input_list(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod, "verified_fixture_presence", lambda _: True)
    monkeypatch.setattr(mod, "verify_dlc", lambda _: True)
    sdk = tmp_path / mod.SDK_VERSION
    sdk.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    native = tmp_path / "native"
    native.mkdir()
    (native / "input_native_u8.raw").write_bytes(mod.native_input())
    (native / "input_list_native.txt").write_text("../../../production.bin\n")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw:
                        pytest.fail("unexpected process"))
    r = mod.trial(sdk, tmp_path / "synthetic.dlc", source,
                  native, tmp_path / "out")
    assert r["status"] == "reject-native-input-list"


def test_cpu_output_scan_disallows_symlink_and_oversize(tmp_path):
    result = tmp_path / "Result_0"
    result.mkdir()
    (result / "one.raw").write_bytes(b"\x00" * 64)
    assert len(mod.bounded_output_files(tmp_path)) == 1
    large = result / "large.raw"
    with large.open("wb") as out:
        out.truncate(mod.MAX_OUTPUT_BYTES + 1)
    assert mod.bounded_output_files(tmp_path) == []


def test_cpu_output_numeric_parity_and_error_are_strict():
    np = pytest.importorskip("numpy")
    expected = np.array([0.0, mod.OUTPUT_SCALE, 2 * mod.OUTPUT_SCALE] +
                        [0.0] * 61, dtype=np.float32)
    raw = bytes([0, 1, 2] + [0] * 61)
    r = mod.compare_native_outputs(raw, expected)
    assert r["status"] == "cpu-matches-onnx-reference"
    assert r["matches"] is True
    assert r["nonzero_output_values"] == 2
    fail = mod.compare_native_outputs(bytes([255] * 64), expected)
    assert fail["matches"] is False
    assert fail["status"] == "cpu-output-differs-from-onnx"


def test_wrong_number_of_native_output_values_rejected():
    np = pytest.importorskip("numpy")
    r = mod.compare_native_outputs(b"\x00" * 128, np.zeros(64))
    assert r["status"] == "reject-output-size"
    assert r["matches"] is False


def test_cpu_runner_never_calls_network_or_production(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod, "verified_fixture_presence", lambda _: True)
    monkeypatch.setattr(mod, "verify_dlc", lambda _: True)
    sdk = tmp_path / mod.SDK_VERSION
    toolbin = sdk / "bin" / "x86_64-linux-clang"
    libbin = sdk / "lib" / "x86_64-linux-clang"
    toolbin.mkdir(parents=True)
    libbin.mkdir(parents=True)
    for tool in ("qnn-net-run",):
        (toolbin / tool).write_bytes(b"dummy tool")
    for name in ("libQnnCpu.so", "libQnnModelDlc.so"):
        (libbin / name).write_bytes(b"dummy lib")
    source = tmp_path / "source"
    source.mkdir()
    native = tmp_path / "native"
    native.mkdir()
    (native / "input_native_u8.raw").write_bytes(mod.native_input())
    (native / "input_list_native.txt").write_text("input_native_u8.raw\n")
    out = tmp_path / "qnn_out"
    observed = []
    def fake_run(argv, **kwargs):
        observed.append((argv, kwargs))
        assert "libQnnCpu.so" in " ".join(argv)
        assert "--use_native_input_files" in argv
        assert kwargs["timeout"] == mod.MAX_RUN_SECONDS
        assert kwargs["cwd"] == native
        return SimpleNamespace(returncode=1, stdout="", stderr="")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    r = mod.trial(sdk, tmp_path / "synthetic.dlc", source, native, out)
    assert len(observed) == 1
    assert r["status"] == "cpu-net-run-nonzero"
    assert r["htp_context_built"] is False
    assert r["htp_executed"] is False
    assert r["ventuno_services_modified"] is False
