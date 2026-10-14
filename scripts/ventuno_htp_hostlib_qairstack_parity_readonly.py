"""Read-only library selector inode parity and QAIRT DLC/runtime provenance.

Compares the legacy 3-library QNN HTP selector with exact installed
/usr/lib targets. Does not run QNN, open /dev, load any host library or
export paths, filesystem inodes, usernames, environment or raw outputs.
"""
import json
from pathlib import Path
import stat

from scripts.ventuno_tiny_qnn_htp_once import LIBS, _find_libraries
from scripts.ventuno_qairt_v75_package_readonly import package_versions
from scripts.qairt_245_dlc_static_audit import verify_fixture, DEFAULT_FIXTURE


HOST_ROOT = Path("/usr/lib")
EXPECTED_FIXTURE_QAIRT_MINOR = "2.45"
HOST_NAMES = ("libQnnHtp.so", "libQnnHtpV75Stub.so", "libQnnModelDlc.so")


def regular_identity(path):
    """Compute internal dev/inode only; never emit an identifier."""
    if path is None:
        return None
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.lstat()
    except (OSError, RuntimeError, ValueError):
        return None
    if not stat.S_ISREG(metadata.st_mode):
        return None
    return metadata.st_dev, metadata.st_ino


def compare_libraries(selected, host_root=HOST_ROOT):
    """Compare exact filename->inode mappings; absence stays unknown."""
    findings = {}
    for name in HOST_NAMES:
        selected_path = selected.get(name)
        packaged = host_root / name
        target_inode = regular_identity(packaged)
        chosen_inode = regular_identity(selected_path)
        findings[name] = {
            "selector_found_file": selected_path is not None,
            "packaged_regular_file": target_inode is not None,
            "selector_regular_file": chosen_inode is not None,
            "selector_matches_packaged_inode": (
                chosen_inode == target_inode
                if chosen_inode is not None and target_inode is not None else None
            ),
        }
    all_matched = all(
        findings[n]["selector_matches_packaged_inode"] is True for n in HOST_NAMES
    )
    return findings, all_matched


def runtime_version_packages(probe=None):
    packages = package_versions() if probe is None else probe
    runtime = {
        name: packages.get(name, {"status": "unknown", "version": None})
        for name in ("qairt-libs", "qairt-dsp-binaries")
    }
    versions = [
        x.get("version") for x in runtime.values()
        if x.get("status") == "installed" and isinstance(x.get("version"), str)
    ]
    both_installed = len(versions) == 2
    versions_equal = both_installed and len(set(versions)) == 1
    matched_minor = (
        versions_equal and versions[0].startswith(EXPECTED_FIXTURE_QAIRT_MINOR + ".")
    )
    return {
        "runtime_packages": runtime,
        "both_runtime_packages_installed": both_installed,
        "runtime_package_versions_match_each_other": versions_equal,
        "fixture_generated_qairstack_minor": EXPECTED_FIXTURE_QAIRT_MINOR,
        "fixture_and_runtime_minor_match": matched_minor if both_installed else None,
        "cross_minor_htp_compatibility_proven": False,
    }


def report(selected=None, host_root=HOST_ROOT, packages=None):
    selected = _find_libraries() if selected is None else selected
    files, same = compare_libraries(selected, host_root)
    fixture = verify_fixture(DEFAULT_FIXTURE)
    return {
        "probe": "ventuno_htp_host_libraries_and_qairt_fixture_readonly",
        "library_comparison": files,
        "all_host_libraries_selected_from_exact_packaged_inodes": same,
        "fixture_dlc_identity_verified": fixture.get("file_identity_verified") is True,
        "qairt_provenance": runtime_version_packages(packages),
        "validated_htp_model_or_operator_support": False,
        "htp_or_qnn_executed": False,
        "device_opened": False,
        "production_modified": False,
        "raw_library_paths_or_inode_numbers_exported": False,
    }


if __name__ == "__main__":
    print("MYAI_HTP_HOSTLIB_PARITY_JSON=" + json.dumps(report(), sort_keys=True))
