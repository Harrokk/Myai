"""Pure synthetic output checks. Tests never start QNN, DSP or a model."""
import hashlib
import inspect
import json

from scripts import ventuno_qnn_native_result_attestation as verify
from scripts import ventuno_qnn_cpu_reference_once as cpu
from scripts import ventuno_tiny_qnn_htp_once as htp


def make_result(tmp_path, data):
    folder = tmp_path / "results" / "Result_0"
    folder.mkdir(parents=True)
    (folder / "result.raw").write_bytes(data)
    return folder


def test_cpu_reference_digest_kept_identical_to_previous_verified_result():
    assert verify.EXPECTED_X86_CPU_RAW_SHA == cpu.EXPECTED_X86_CPU_RAW_SHA


def test_exact_reference_match_still_never_claims_npu():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        data = bytes(range(64))
        make_result(root, data)
        output = verify.attest_native_output(
            root, expected_sha=hashlib.sha256(data).hexdigest()
        )
        assert output["status"] == (
            "cpu_reference_digest_match_but_placement_unverified"
        )
        assert output["native_64_byte_output_present"] is True
        assert output["output_matches_verified_cpu_reference"] is True
        assert output["htp_operator_placement_verified"] is False
        assert output["npu_execution_verified"] is False
        assert "result.raw" not in json.dumps(output)


def test_arbitrary_nonzero_64_bytes_are_not_verified():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        make_result(root, b"X" * 64)
        result = verify.attest_native_output(
            root, expected_sha="0" * 64
        )
        assert result["native_64_byte_output_present"] is True
        assert result["output_matches_verified_cpu_reference"] is False
        assert result["status"] == "nonzero_output_differs_from_cpu_reference"
        assert result["npu_execution_verified"] is False


def test_all_zero_output_cannot_pass_even_with_matching_hash(tmp_path):
    raw = bytes(64)
    make_result(tmp_path, raw)
    result = verify.attest_native_output(
        tmp_path, expected_sha=hashlib.sha256(raw).hexdigest()
    )
    assert result["status"] == "all_zero_output"
    assert result["output_matches_verified_cpu_reference"] is False


def test_missing_short_and_long_outputs_are_rejected(tmp_path):
    assert verify.attest_native_output(tmp_path)["native_64_byte_output_present"] is False
    folder = make_result(tmp_path, b"A" * 63)
    assert verify.attest_native_output(tmp_path)["status"] == "wrong_native_output_size"
    (folder / "result.raw").write_bytes(b"A" * 65)
    assert verify.attest_native_output(tmp_path)["status"] == "wrong_native_output_size"


def test_ambiguous_outputs_never_pass(tmp_path):
    folder = make_result(tmp_path, b"A" * 64)
    (folder / "other.raw").write_bytes(b"B" * 64)
    result = verify.attest_native_output(tmp_path)
    assert result["status"] == "ambiguous_raw_outputs"
    assert result["npu_execution_verified"] is False


def test_symlinked_results_are_rejected(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "sensitive.raw").write_bytes(b"A" * 64)
    results = tmp_path / "results"
    results.mkdir()
    (results / "Result_0").symlink_to(target, target_is_directory=True)
    result = verify.attest_native_output(tmp_path)
    assert result["status"] == "missing_or_untrusted_result_directory"
    assert "elsewhere" not in json.dumps(result)


def test_symlinked_raw_file_never_read(tmp_path):
    folder = tmp_path / "results" / "Result_0"
    folder.mkdir(parents=True)
    outside = tmp_path / "secret.raw"
    outside.write_bytes(b"S" * 64)
    (folder / "result.raw").symlink_to(outside)
    assert verify.attest_native_output(tmp_path)["status"] == (
        "missing_or_untrusted_raw_output"
    )


def test_result_directory_entries_are_bounded(tmp_path):
    folder = make_result(tmp_path, b"A" * 64)
    for n in range(verify.MAX_DIRECTORY_ENTRIES):
        (folder / ("extra_" + str(n) + ".txt")).write_bytes(b"")
    assert verify.attest_native_output(tmp_path)["status"] == "directory_entry_limit"


def test_invalid_expected_reference_never_attests(tmp_path):
    make_result(tmp_path, b"A" * 64)
    for value in (None, "not-a-digest", "A" * 64, "x" * 64):
        assert verify.attest_native_output(tmp_path, value)["status"] == (
            "invalid_reference_digest"
        )


def test_htp_diagnostic_does_not_claim_inference_on_nonzero_result():
    src = inspect.getsource(htp.run_once)
    assert "attest_native_output(root)" in src
    assert 'result["htp_inference_verified"] = True' not in src
    assert 'result["htp_operator_placement_verified"] = True' not in src
    assert 'tiny_qnn_htp_native_inference_succeeded' not in src
