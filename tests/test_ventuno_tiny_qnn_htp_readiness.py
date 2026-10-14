"""No-inference QAIRT small sample preflight tests."""
from scripts.ventuno_tiny_qnn_htp_readiness import library_presence


def test_library_probe_finds_regular_files_without_exposing_paths(tmp_path):
    (tmp_path / "sdk").mkdir()
    (tmp_path / "sdk" / "libQnnHtp.so").write_bytes(b"dummy")
    (tmp_path / "sdk" / "libQnnModelDlc.so").write_bytes(b"dummy")
    found, limits = library_presence((tmp_path,))
    assert found["libQnnHtp.so"] is True
    assert found["libQnnModelDlc.so"] is True
    assert found["libQnnCpu.so"] is False
    assert "sdk" not in str(found)
    assert limits["directories_visited"] >= 2


def test_library_probe_does_not_follow_symlinked_sdk_tree(tmp_path):
    outside = tmp_path / "other"
    outside.mkdir()
    (outside / "libQnnHtp.so").write_bytes(b"dummy")
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    found, limits = library_presence((link,))
    assert not any(found.values())
    assert limits["directories_visited"] == 0
