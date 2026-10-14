"""Validate strict distro QNN host-library gate by metadata only.

This imports the experimental selector but never calls run_once/QNN.
Only safe Boolean outputs; no path, file identifier or vendor logs.
"""
import json

from scripts.ventuno_tiny_qnn_htp_once import LIBS, _find_libraries


def report():
    selected = _find_libraries()
    return {
        "probe": "ventuno_htp_hostlib_failclosed_metadata_only",
        "packaged_aarch64_host_libraries": {
            name: name in selected for name in LIBS
        },
        "all_three_packaged_host_libraries_verified": all(
            name in selected for name in LIBS
        ),
        "legacy_fallback_selection_disabled_in_experimental_gate": True,
        "htp_model_compatibility_verified": False,
        "htp_or_qnn_executed": False,
        "device_opened": False,
        "production_modified": False,
        "raw_paths_or_inode_numbers_exported": False,
    }


if __name__ == "__main__":
    print("MYAI_STRICT_HTP_HOSTLIB_JSON=" + json.dumps(report(), sort_keys=True))
