"""Bounded cached HTP weight-sharing key inventory regression tests."""
import json

from scripts.ventuno_qnn_weight_sharing_inventory import (
    scan_roots, summarize_declaration,
)


def test_enabled_value_works_in_nested_context():
    assert summarize_declaration({"context": {"weight_sharing_enabled": True}}) == "declared-enabled"


def test_disabled_is_not_silent_success():
    assert summarize_declaration({"context": {"weightSharingEnabled": False}}) == "declared-disabled"


def test_absent_setting_is_inconclusive():
    assert summarize_declaration({"context": {"graphs": []}}) == "not-declared"


def test_conflicting_settings_rejected():
    val = {"context": {"weight_sharing_enabled": True},
           "other": {"weightSharingEnabled": False}}
    assert summarize_declaration(val) == "conflicting-or-invalid"


def test_wrong_types_rejected_even_when_truthy():
    assert summarize_declaration({"weight_sharing_enabled": "true"}) == "conflicting-or-invalid"
    assert summarize_declaration({"weight_sharing_enabled": 1}) == "conflicting-or-invalid"


def test_nested_graph_arrays_are_traversed():
    val = {"graphs": [{"context": {"weight_sharing_enabled": True}}]}
    assert summarize_declaration(val) == "declared-enabled"


def test_fixture_inventory_reports_status_not_paths(tmp_path):
    nested = tmp_path / "cache" / "some-model"
    nested.mkdir(parents=True)
    file = nested / "htp_backend_ext_config.json"
    file.write_text(json.dumps({"context": {"weight_sharing_enabled": True}}))
    report = scan_roots((tmp_path,))
    assert report["files_inspected"] == 1
    assert report["declaration_status_counts"]["declared-enabled"] == 1
    assert "some-model" not in json.dumps(report)
    assert report["runtime_weight_sharing_proven"] is False
    assert report["safe_to_start_second_model"] is False


def test_symlinked_config_is_ignored(tmp_path):
    import pytest
    original = tmp_path / "elsewhere.json"
    original.write_text('{"weight_sharing_enabled": true}')
    try:
        (tmp_path / "htp_backend_ext_config.json").symlink_to(original)
    except OSError:
        pytest.skip("symlinks unavailable")
    result = scan_roots((tmp_path,))
    assert result["files_inspected"] == 0


def test_invalid_json_is_sanitized(tmp_path):
    file = tmp_path / "htp_backend_ext_config.json"
    file.write_text("{a-private-token")
    result = scan_roots((tmp_path,))
    assert result["declaration_status_counts"] == {"unreadable-or-invalid-json": 1}
    assert "private" not in json.dumps(result)
