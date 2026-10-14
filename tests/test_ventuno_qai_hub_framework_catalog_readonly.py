"""Offline Qualcomm framework snapshot parser tests; never calls AI Hub."""
import json

from scripts import ventuno_qai_hub_framework_catalog_readonly as check


def framework(name="QAIRT", version="2.46", full="2.46.0.260800", tags=None):
    return {
        "name": name, "api_version": version,
        "full_version": full, "api_tags": [] if tags is None else tags,
    }


def encoded(*records):
    return json.dumps({"frameworks": list(records)}).encode("utf-8")


def test_without_snapshot_is_explicit_no_go():
    report = check.inspect_snapshot_file(None)
    assert report["status"] == "no_go_catalog_snapshot_not_supplied"
    assert report["qairt_246_in_supplied_snapshot"] is None
    assert report["catalog_live_authenticity_verified"] is False


def test_exact_qairt_246_snapshot_reports_presence_but_not_live():
    report = check.inspect_snapshot_bytes(
        encoded(framework(version="2.45", full="2.45.0.260300"),
                framework(version="2.46", full="2.46.0.260800",
                          tags=["default"]),
                framework(version="2.50", full="2.50.0.260828",
                          tags=["latest"]))
    )
    assert report["normalized_snapshot_schema_valid"] is True
    assert report["qairt_246_in_supplied_snapshot"] is True
    assert report["qairt_246_full_version_pattern_consistent"] is True
    assert report["status"] == "snapshot_lists_246_live_availability_unverified"
    assert report["catalog_live_authenticity_verified"] is False
    assert report["exact_ventuno_target_support_for_246_verified"] is False
    assert report["model_uploaded"] is False
    assert report["compile_or_link_job_submitted"] is False


def test_other_versions_do_not_establish_246():
    report = check.inspect_snapshot_bytes(
        encoded(framework(version="2.45", full="2.45.0"),
                framework(version="2.50", full="2.50.0"))
    )
    assert report["qairt_246_in_supplied_snapshot"] is False
    assert report["status"] == "snapshot_does_not_list_246_not_live_proof"


def test_nonqairt_framework_at_246_is_not_qairt():
    r = check.inspect_snapshot_bytes(
        encoded(framework(name="ONNX", version="2.46", full="2.46.0"))
    )
    assert r["qairt_246_in_supplied_snapshot"] is False


def test_false_version_match_with_inconsistent_full_version():
    r = check.inspect_snapshot_bytes(
        encoded(framework(version="2.46", full="2.50.0"))
    )
    assert r["status"] == "no_go_framework_version_inconsistency"
    assert r["qairt_246_full_version_pattern_consistent"] is False


def test_ambiguous_duplicate_246_records_fail_closed():
    r = check.inspect_snapshot_bytes(encoded(framework(), framework()))
    assert r["status"] == "no_go_ambiguous_duplicate_qairt_246_versions"
    assert r["qairt_246_in_supplied_snapshot"] is None


def test_unexpected_keys_and_secret_fields_are_rejected_not_logged():
    obj = framework()
    obj["api_token"] = "SECRET"
    r = check.inspect_snapshot_bytes(encoded(obj))
    assert r["status"] == "no_go_invalid_framework_record"
    assert "SECRET" not in json.dumps(r)
    assert "api_token" not in json.dumps(r)


def test_duplicate_json_object_keys_and_invalid_utf8_rejected():
    r = check.inspect_snapshot_bytes(
        b'{"frameworks":[{"name":"QAIRT","name":"QAIRT",'
        b'"api_version":"2.46","full_version":"2.46.0","api_tags":[]}]}'
    )
    assert r["status"] == "no_go_unparseable_or_duplicate_json"
    assert check.inspect_snapshot_bytes(b"\xff\xfe")["status"] == (
        "no_go_unparseable_or_duplicate_json"
    )


def test_oversized_empty_or_flooded_catalog_rejected():
    assert check.inspect_snapshot_bytes(b"")["status"] == "no_go_invalid_snapshot_length"
    assert check.inspect_snapshot_bytes(b"x" * (check.MAX_SNAPSHOT_BYTES + 1))[
        "status"
    ] == "no_go_invalid_snapshot_length"
    assert check.inspect_snapshot_bytes(encoded(*[framework(version="2.45", full="2.45.0")] * (check.MAX_ENTRIES + 1)))["status"] == "no_go_invalid_snapshot_schema"


def test_untrusted_symlink_and_file_size_rejected(tmp_path):
    actual = tmp_path / "snapshot.json"
    actual.write_bytes(encoded(framework()))
    link = tmp_path / "symlink.json"
    link.symlink_to(actual)
    assert check.inspect_snapshot_file(link)["status"] == "no_go_untrusted_snapshot_file"
    assert check.inspect_snapshot_file(actual)["status"] == (
        "snapshot_lists_246_live_availability_unverified"
    )
    actual.write_bytes(b"x" * (check.MAX_SNAPSHOT_BYTES + 1))
    assert check.inspect_snapshot_file(actual)["status"] == "no_go_untrusted_snapshot_file"


def test_tag_validation_avoids_user_injected_text():
    r = check.inspect_snapshot_bytes(
        encoded(framework(tags=["latest", "token=SECRET"]))
    )
    assert r["status"] == "no_go_invalid_framework_value"
    assert "SECRET" not in json.dumps(r)


def test_exact_catalog_record_never_proves_backend_acceptance():
    r = check.inspect_snapshot_bytes(encoded(framework()))
    assert r["catalog_freshness_verified"] is False
    assert r["cloud_request_performed"] is False
    assert r["api_credentials_accessed"] is False
    assert r["model_graph_or_operator_compatibility_verified"] is False
    assert r["npu_executed"] is False
    assert r["production_modified"] is False
