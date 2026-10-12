"""Safety tests for metadata-only tiny QAIRT sample discovery."""
import json
from pathlib import Path

import pytest

from scripts.ventuno_qnn_microprofile_inventory import (
    MAX_SAMPLE_BYTES, candidate_inventory, installed_tools,
    readiness_report, sample_tree,
)


def test_sdk_example_path_required_for_candidates():
    assert sample_tree(Path("examples/Models/Tiny/model.dlc"))
    assert sample_tree(Path("third-party/samples/basic/model.bin"))
    assert not sample_tree(Path("geniex/cache/model.bin"))
    assert not sample_tree(Path("arbitrary/model.onnx"))


def test_collect_small_samples_without_reading_bytes(tmp_path):
    sample = tmp_path / "SDK" / "examples" / "Models" / "Tiny"
    sample.mkdir(parents=True)
    (sample / "tiny.dlc").write_bytes(b"fake-format")
    (sample / "tiny.onnx").write_bytes(b"not-onnx")
    (sample / "tiny.bin").write_bytes(b"arbitrary")
    (sample / "input_list.txt").write_text("value.raw\n")
    out = candidate_inventory((tmp_path / "SDK",))
    assert out["small_example_artifact_counts"] == {
        "bin-unverified": 1, "dlc": 1, "onnx": 1,
    }
    assert out["example_input_list_found"] is True
    assert out["independent_compatible_context_verified"] is False
    assert out["authorization_to_run_qnn"] is False
    assert out["htp_profile_measurement_verified"] is False


def test_ignore_nonsample_model_cache_even_inside_roots(tmp_path):
    target = tmp_path / "cache" / "Qwen3"
    target.mkdir(parents=True)
    (target / "production.bin").write_bytes(b"fake")
    out = candidate_inventory((tmp_path,))
    assert out["small_example_artifact_counts"] == {}


def test_large_sample_is_not_considered_safe_candidate(tmp_path):
    sample = tmp_path / "examples"
    sample.mkdir()
    with (sample / "huge.bin").open("wb") as handle:
        handle.truncate(MAX_SAMPLE_BYTES + 1)
    out = candidate_inventory((tmp_path,))
    assert out["small_example_artifact_counts"] == {}
    assert out["oversize_or_empty_artifact_counts"] == {
        "bin-unverified": 1
    }


def test_symlink_avoids_following_external_model(tmp_path):
    sample = tmp_path / "examples"
    sample.mkdir()
    external = tmp_path / "secret.bin"
    external.write_bytes(b"private")
    try:
        (sample / "other.bin").symlink_to(external)
    except OSError:
        pytest.skip("symlinks unsupported")
    out = candidate_inventory((tmp_path,))
    assert out["small_example_artifact_counts"] == {}


def test_scan_limits_fail_closed(tmp_path):
    root = tmp_path / "examples"
    root.mkdir()
    for index in range(10):
        (root / f"{index}.dlc").write_bytes(b"x")
    out = candidate_inventory((tmp_path,), max_files=3)
    assert out["scan_capped"] is True
    assert readiness_report({}, out)["status"] == "inconclusive-sdk-inventory"
    assert readiness_report({}, out)["npu_profiling_go"] is False


def test_directory_limit_validation():
    for bad in (-1, 0, 999999, True):
        with pytest.raises(ValueError, match="invalid-directory-cap"):
            candidate_inventory((), max_dirs=bad)


def test_small_candidate_requires_compatibility_checks():
    result = readiness_report(
        {"qnn-net-run": True},
        {"small_example_artifact_counts": {"dlc": 1}, "scan_capped": False,
         "unreadable_entries": False},
    )
    assert result["status"] == "candidate-needs-format-and-runtime-validation"
    assert result["npu_profiling_go"] is False
    assert result["production_contexts_usable_as_test_sample"] is False


def test_no_sample_with_converter_is_still_no_go():
    r = readiness_report(
        {"qnn-onnx-converter": True, "qnn-context-binary-generator": True},
        {"small_example_artifact_counts": {}, "scan_capped": False,
         "unreadable_entries": False},
    )
    assert r["status"] == "host-standalone-sample-preparation-may-be-possible"
    assert r["npu_profiling_go"] is False


def test_missing_toolchain_and_sample_is_no_go():
    r = readiness_report(
        {}, {"small_example_artifact_counts": {}, "scan_capped": False,
             "unreadable_entries": False}
    )
    assert r["status"] == "no-go-separate-prepared-sample-required"
    assert r["npu_profiling_go"] is False


def test_public_report_never_contains_paths_or_sample_filenames(tmp_path):
    sample = tmp_path / "examples" / "confidential-bert"
    sample.mkdir(parents=True)
    (sample / "private_context.dlc").write_bytes(b"secret bytes")
    out = candidate_inventory((tmp_path,))
    printed = json.dumps(out)
    assert "private_context" not in printed
    assert "confidential-bert" not in printed
    assert str(tmp_path) not in printed
    assert "secret" not in printed


def test_tool_inventory_only_returns_bools():
    assert all(type(v) is bool for v in installed_tools().values())
