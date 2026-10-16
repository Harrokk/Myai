"""All eight sensitive source locations have independent safety contracts."""
import json
from pathlib import Path

from scripts import ventuno_eight_sensitive_calls_review as audit


ROOT = Path(__file__).resolve().parents[1]


def _copy_sources(root):
    for relpath in sorted({row[0] for row in audit.EXPECTED}):
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relpath).read_bytes())


def test_exact_eight_manual_call_sites_have_expected_synthetic_boundaries():
    result = audit.inspect_source(ROOT)
    assert result["status"] == "eight-reviewed-synthetic-sites-catalogued"
    assert result["expected_sites"] == 8
    assert result["actual_sites"] == 8
    assert result["prod_sites"] == 1
    assert result["synthetic_test_sites"] == 7
    assert result["unreviewed_sites"] is False
    assert result["live_model_launched"] is False
    assert result["microphone_or_speaker_opened"] is False
    assert result["test_execution_performed_by_this_script"] is False


def test_missing_review_file_never_claims_safety(tmp_path):
    _copy_sources(tmp_path)
    (tmp_path / "core" / "voice_stt_persistent.py").unlink()
    result = audit.inspect_source(tmp_path)
    assert result["unreviewed_sites"] is True


def test_extra_risky_call_in_test_file_fails_closed(tmp_path):
    _copy_sources(tmp_path)
    path = tmp_path / "tests" / "test_voice_process_census.py"
    path.write_text(path.read_text() + "\ndef synthetic_extra():\n    subprocess.Popen(['unexpected'])\n")
    assert audit.inspect_source(tmp_path)["status"] == (
        "fail-closed-unreviewed-sensitive-call"
    )


def test_unreviewed_production_worker_environment_change_blocks(tmp_path):
    _copy_sources(tmp_path)
    path = tmp_path / "core" / "voice_stt_persistent.py"
    source = path.read_text()
    assert "start_new_session=True" in source
    path.write_text(source.replace("start_new_session=True", "start_new_session=False"))
    assert audit.inspect_source(tmp_path)["unreviewed_sites"] is True


def test_unreviewed_production_worker_shell_execution_change_blocks(tmp_path):
    _copy_sources(tmp_path)
    path = tmp_path / "core" / "voice_stt_persistent.py"
    source = path.read_text()
    assert "bufsize=0, start_new_session=True" in source
    path.write_text(source.replace(
        "bufsize=0, start_new_session=True",
        "bufsize=0, shell=True, start_new_session=True",
    ))
    assert audit.inspect_source(tmp_path)["unreviewed_sites"] is True


def test_test_exec_must_consume_checked_in_metric_source(tmp_path):
    _copy_sources(tmp_path)
    path = tmp_path / "tests" / "test_ventuno_whisper_base_swedish_comparison.py"
    source = path.read_text()
    assert "exec(compare._METRIC_SOURCE,namespace)" in source
    path.write_text(source.replace(
        "exec(compare._METRIC_SOURCE,namespace)", "exec(untrusted_source,namespace)",
    ))
    assert audit.inspect_source(tmp_path)["unreviewed_sites"] is True


def test_parser_error_and_symlink_fail_closed(tmp_path):
    _copy_sources(tmp_path)
    path = tmp_path / "tests" / "test_voice_stt_process.py"
    path.unlink()
    path.symlink_to(ROOT / "tests" / "test_voice_stt_process.py")
    assert audit.inspect_source(tmp_path)["unreviewed_sites"] is True
    path.unlink()
    path.write_text("this is not valid python :(\n")
    assert audit.inspect_source(tmp_path)["unreviewed_sites"] is True


def test_sanitized_report_contains_only_counts_categories_and_fixed_flags():
    result = audit.inspect_source(ROOT)
    text = json.dumps(result)
    assert "HF_HUB_TOKEN" not in text
    assert "SYNTHETIC_PRIVATE_AUDIO" not in text
    assert "/home/" not in text
    assert "worker argv" not in text
    assert all(isinstance(x, (str, bool, int)) for x in result.values())
