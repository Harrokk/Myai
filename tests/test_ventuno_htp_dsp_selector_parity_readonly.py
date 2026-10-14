"""Offline unit tests: only synthetic directories and stubbed selection."""
import json
from scripts import ventuno_htp_dsp_selector_parity_readonly as probe


def test_legacy_selector_matches_same_inode(tmp_path):
    folder = tmp_path / "dsp"
    folder.mkdir()
    canonical = folder / "libQnnHtpV75Skel.so"
    binary = folder / "target.so"
    binary.write_bytes(b"fake")
    canonical.symlink_to(binary)
    result = probe.compare_selector(canonical, selection=lambda: folder)
    assert result["legacy_selector_found_candidate"] is True
    assert result["legacy_selected_same_inode_as_packaged_skel"] is True
    assert result["any_dsp_or_qnn_executed"] is False


def test_legacy_selector_alternate_copy_mismatch(tmp_path):
    vendor = tmp_path / "vendor"
    fallback = tmp_path / "fallback"
    vendor.mkdir()
    fallback.mkdir()
    canonical = vendor / "libQnnHtpV75Skel.so"
    canonical.write_bytes(b"packaged")
    (fallback / canonical.name).write_bytes(b"other")
    result = probe.compare_selector(canonical, selection=lambda: fallback)
    assert result["legacy_selected_same_inode_as_packaged_skel"] is False
    assert result["legacy_candidate_regular"] is True
    assert result["historical_qnn_attempt_selected_file_identity_proven"] is False
    assert str(tmp_path) not in json.dumps(result)


def test_missing_fallback_never_assumes_mismatch(tmp_path):
    canonical = tmp_path / "libQnnHtpV75Skel.so"
    canonical.write_bytes(b"fake")
    result = probe.compare_selector(canonical, selection=lambda: None)
    assert result["legacy_selector_found_candidate"] is False
    assert result["legacy_selected_same_inode_as_packaged_skel"] is None


def test_missing_packaged_path_is_unknown(tmp_path):
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    (fallback / "libQnnHtpV75Skel.so").write_bytes(b"other")
    result = probe.compare_selector(tmp_path / "libQnnHtpV75Skel.so",
                                    selection=lambda: fallback)
    assert result["canonical_packaged_skel_regular"] is False
    assert result["legacy_selected_same_inode_as_packaged_skel"] is None


def test_regular_file_required(tmp_path):
    target = tmp_path / "directory"
    target.mkdir()
    assert probe.inode_of_regular(target) is None
    dangling = tmp_path / "link"
    dangling.symlink_to("missing")
    assert probe.inode_of_regular(dangling) is None
