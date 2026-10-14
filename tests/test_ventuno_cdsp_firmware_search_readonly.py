"""Synthetic-only CDSP firmware search metadata tests; never open firmware."""
import json

from scripts import ventuno_cdsp_firmware_search_readonly as probe


def make_cdsp(tmp_path, firmware="qcom/vendor/cdsp.mbn", state="running"):
    remote = tmp_path / "sys" / "remoteproc0"
    dt = remote / "device" / "of_node"
    dt.mkdir(parents=True)
    (remote / "name").write_text("opaque-remoteproc")
    (dt / "compatible").write_bytes(b"qcom,monaco-cdsp-pas\0qcom,pas\0")
    (remote / "state").write_text(state)
    (remote / "firmware").write_text(firmware)
    return remote.parent


def test_rejects_absolute_traversal_hidden_or_large_firmware_names():
    for value in (None, "", "/etc/passwd", "../secret", "a/../../secret",
                  "a//b", "a/./b", "private key", "x" * 193, "a/\x00b",
                  ".hidden", "a/.hidden"):
        assert probe.verified_firmware_name(value) is None
    assert probe.verified_firmware_name("qcom/monaco/cdsp.mbn") == [
        "qcom", "monaco", "cdsp.mbn",
    ]


def test_firmware_regular_candidate_and_no_path_leak(tmp_path):
    root = tmp_path / "lib" / "firmware"
    artifact = root / "qcom" / "vendor" / "cdsp.mbn"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"DO_NOT_READ_FIRMWARE")
    remote = make_cdsp(tmp_path)
    output = probe.report(remoteproc_root=remote, firmware_root=root,
                          custom_path=tmp_path / "custom_missing")
    assert output["cdsp_identity"] == "one_running_cdsp"
    assert output["sysfs_firmware_name_validated"] is True
    assert output["firmware_filesystem_search"] == "regular_candidate_found"
    assert output["candidate_metadata"]["existing_regular_files"] == 1
    assert output["no_firmware_contents_read"] is True
    assert output["no_device_node_opened"] is True
    encoded = json.dumps(output)
    assert "DO_NOT_READ" not in encoded
    assert "qcom/vendor" not in encoded
    assert str(tmp_path) not in encoded


def test_missing_regular_files_do_not_prove_missing_running_firmware(tmp_path):
    root = tmp_path / "firmware"
    root.mkdir()
    remote = make_cdsp(tmp_path)
    observed = probe.report(remoteproc_root=remote, firmware_root=root)
    assert observed["cdsp_running"] is True
    assert observed["firmware_filesystem_search"] == (
        "no_regular_candidate_in_sampled_paths"
    )
    assert observed["actual_firmware_image_running_identity_proven"] is False
    assert observed["initramfs_firmware_presence_verified"] is False


def test_symlink_escape_refused_as_regular_candidate(tmp_path):
    root = tmp_path / "firmware"
    root.mkdir()
    outside = tmp_path / "private.mbn"
    outside.write_bytes(b"SECRET")
    path = root / "cdsp.mbn"
    path.symlink_to(outside)
    counts = probe.candidate_metadata(["cdsp.mbn"], root, release="6.8.0-qcom")
    assert counts["existing_regular_files"] == 0
    assert counts["out_of_tree_links"] == 1


def test_firmware_candidate_under_kernel_release_path(tmp_path):
    root = tmp_path / "firmware"
    image = root / "updates" / "6.8-qcom" / "qcom" / "cdsp.mbn"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"x")
    output = probe.candidate_metadata(["qcom", "cdsp.mbn"], root,
                                      release="6.8-qcom")
    assert output["existing_regular_files"] == 1
    assert output["checked"] == 4


def test_ambiguous_remoteproc_does_not_guess_firmware(tmp_path):
    remote = make_cdsp(tmp_path)
    clone = remote / "remoteproc1"
    dt = clone / "device" / "of_node"
    dt.mkdir(parents=True)
    (clone / "name").write_text("cdsp")
    assert probe.cdsp_entry(remote)[0] == "ambiguous"
    output = probe.report(remoteproc_root=remote, firmware_root=tmp_path)
    assert output["firmware_filesystem_search"] == "not_checked"
    assert output["cdsp_running"] is False


def test_unvalidated_name_skips_search(tmp_path):
    root = tmp_path / "firmware"
    root.mkdir()
    remote = make_cdsp(tmp_path, firmware="../private")
    output = probe.report(remoteproc_root=remote, firmware_root=root)
    assert output["firmware_filesystem_search"] == "invalid_or_unavailable_name"
    assert output["candidate_metadata"] is None
    assert "../private" not in json.dumps(output)


def test_nonrunning_cdsp_skips_firmware_candidate_read(tmp_path):
    remote = make_cdsp(tmp_path, state="offline")
    result = probe.report(remoteproc_root=remote, firmware_root=tmp_path)
    assert result["cdsp_identity"] == "not_running"
    assert result["candidate_metadata"] is None


def test_custom_search_parameter_only_boolean_category(tmp_path):
    p = tmp_path / "path"
    p.write_text("/secret/firmware/private-directory")
    assert probe.custom_path_indicator(p) == "configured"
    p.write_text("")
    assert probe.custom_path_indicator(p) == "empty"
    assert probe.custom_path_indicator(tmp_path / "missing") == "unavailable"
