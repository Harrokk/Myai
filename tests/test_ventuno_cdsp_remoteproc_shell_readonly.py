"""Purely synthetic CDSP sysfs and FastRPC shell metadata tests."""
import json
from scripts import ventuno_cdsp_remoteproc_shell_readonly as probe


def test_dsp_names_use_boundaries_not_substrings():
    assert probe.classify_dsp_label("remoteproc-cdsp") == "cdsp"
    assert probe.classify_dsp_label("qcom/adsp") == "adsp"
    assert probe.classify_dsp_label("qccdsp") == "unclassified"
    assert probe.classify_dsp_label("mycdspdevice") == "unclassified"
    assert probe.classify_dsp_label(None) == "unknown"


def test_one_cdsp_running_uses_only_bounded_sysfs(tmp_path):
    root = tmp_path / "remoteproc"
    cdsp = root / "remoteproc0"
    adsp = root / "remoteproc1"
    cdsp.mkdir(parents=True)
    adsp.mkdir()
    (cdsp / "name").write_text("qcom-cdsp\n")
    (cdsp / "state").write_text("running\n")
    (cdsp / "firmware").write_text("vendor/cdsp.mbn\n")
    (adsp / "name").write_text("qcom-adsp\n")
    result = probe.remoteprocs(root)
    assert result["remoteproc_count"] == 2
    assert result["cdsp_count"] == 1
    assert result["cdsp_state"] == "running"
    assert result["cdsp_firmware_attribute_readable"] is True
    assert result["cdsp_firmware_name_looks_like_cdsp"] is True
    assert "vendor" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)


def test_ambiguous_cdsp_does_not_report_arbitrary_state(tmp_path):
    for i in range(2):
        node = tmp_path / f"remoteproc{i}"
        node.mkdir()
        (node / "name").write_text("cdsp")
        (node / "state").write_text("running")
    result = probe.remoteprocs(tmp_path)
    assert result["cdsp_count"] == 2
    assert result["cdsp_state"] == "unknown"
    assert result["cdsp_firmware_attribute_readable"] is None


def test_bounded_firmware_string_unknown_without_leak(tmp_path):
    node = tmp_path / "remoteproc0"
    node.mkdir()
    (node / "name").write_bytes(b"cdsp")
    (node / "state").write_bytes(b"running")
    (node / "firmware").write_bytes(b"SECRET-LOCATION" * 30)
    output = probe.remoteprocs(tmp_path)
    assert output["cdsp_firmware_attribute_readable"] is False
    assert output["cdsp_firmware_name_looks_like_cdsp"] is None
    assert "SECRET" not in json.dumps(output)


def test_more_than_budget_marks_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "MAX_REMOTEPROC", 2)
    for i in range(3):
        (tmp_path / f"remoteproc{i}").mkdir()
    result = probe.remoteprocs(tmp_path)
    assert result["count_complete"] is False
    assert result["remoteproc_count"] == 2


def test_shell_header_outcomes_do_not_expose_paths(tmp_path, monkeypatch):
    recorded = []
    def fake_inspect(path, root):
        recorded.append(str(path))
        return {
            "file_regular": True, "path_inside_usr": True,
            "header_class": "hexagon_elf_header",
            "library_file_header_read": True,
        }
    monkeypatch.setattr(probe, "inspect_resolved_skel", fake_inspect)
    out = probe.shell_headers({"one": tmp_path / "SECRET-PATH"})
    assert out == {"one": {
        "resolved_regular_under_usr": True,
        "elf_architecture": "hexagon_elf_header",
        "file_header_read": True,
    }}
    assert "SECRET" not in json.dumps(out)
    assert len(recorded) == 1


def test_report_never_claims_pd_or_firmware_compatibility(monkeypatch):
    monkeypatch.setattr(probe, "remoteprocs", lambda: {
        "cdsp_count": 1, "cdsp_state": "running",
    })
    monkeypatch.setattr(probe, "shell_headers", lambda: {})
    result = probe.report()
    assert result["firmware_version_or_build_match_proven"] is False
    assert result["signed_unsigned_pd_session_verified"] is False
    assert result["backend_initialization_verified"] is False
    assert result["model_or_npu_run"] is False
    assert result["device_node_opened"] is False


def test_dt_compatible_identifies_cdsp_when_name_is_opaque(tmp_path):
    node = tmp_path / "remoteproc0"
    of = node / "device" / "of_node"
    of.mkdir(parents=True)
    (node / "name").write_text("32300000.remoteproc\n", encoding="ascii")
    (node / "state").write_text("running\n", encoding="ascii")
    (of / "compatible").write_bytes(b"qcom,monaco-cdsp-pas\0qcom,pas\0")
    (node / "firmware").write_text("qcom/cdsp.mbn", encoding="ascii")
    result = probe.remoteprocs(tmp_path)
    assert result["cdsp_count"] == 1
    assert result["cdsp_state"] == "running"
    assert result["cdsp_identification_method"] == "dt_compatible"
    assert result["remoteproc_running_count"] == 1
    assert "32300000" not in json.dumps(result)
    assert "monaco" not in json.dumps(result)


def test_opaque_names_without_dt_cannot_be_assigned_to_cdsp(tmp_path):
    for i in range(2):
        node = tmp_path / f"remoteproc{i}"
        node.mkdir()
        (node / "name").write_text("opaque"+str(i), encoding="ascii")
        (node / "state").write_text("running", encoding="ascii")
    result = probe.remoteprocs(tmp_path)
    assert result["cdsp_count"] == 0
    assert result["cdsp_identification_method"] == "not_identified"
    assert result["remoteproc_running_count"] == 2
    assert result["cdsp_state"] == "unknown"
