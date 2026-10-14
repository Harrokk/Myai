"""Compare legacy tiny-HTP DSP path selection with the packaged V75 Skel.

No model call, no HTP, no device open. Emits only equality/availability
categories, never paths, symlink text, identifiers, env or library bytes.
"""
import json
from pathlib import Path
import stat

from scripts.ventuno_tiny_qnn_htp_once import _find_v75_skel_directory
from scripts.ventuno_htp_v75_skel_link_readonly import SKEL


def inode_of_regular(path):
    try:
        target = path.resolve(strict=True)
        info = target.lstat()
    except (OSError, RuntimeError, ValueError):
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return (info.st_dev, info.st_ino)


def compare_selector(canonical=SKEL, selection=None):
    """Selection is injectable to test without touching actual board paths."""
    canonical_inode = inode_of_regular(canonical)
    if selection is None:
        directory = _find_v75_skel_directory()
    else:
        directory = selection()
    other_inode = (
        inode_of_regular(directory / canonical.name) if directory else None
    )
    return {
        "canonical_packaged_skel_regular": canonical_inode is not None,
        "legacy_selector_found_candidate": directory is not None,
        "legacy_candidate_regular": other_inode is not None,
        "legacy_selected_same_inode_as_packaged_skel": (
            canonical_inode == other_inode
            if canonical_inode is not None and other_inode is not None else None
        ),
        "legacy_selector_includes_canonical_usr_lib_dsp_root": False,
        "historical_qnn_attempt_selected_file_identity_proven": False,
        "any_dsp_or_qnn_executed": False,
        "any_device_opened": False,
        "production_modified": False,
        "raw_paths_exported": False,
    }


if __name__ == "__main__":
    print("MYAI_HTP_DSP_SELECTOR_JSON=" + json.dumps(
        compare_selector(), sort_keys=True
    ))
