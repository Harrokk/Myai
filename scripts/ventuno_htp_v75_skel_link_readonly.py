"""Read-only VENTUNO HTP-v75 skeleton symlink identity and package provenance.

Only lstat/resolve/stat of three fixed allowlisted system-library paths and
dpkg-query ownership metadata. Never opens/loads libs or devices, executes
QNN/GenieX, or exports paths, symlink targets, process IDs or raw dpkg output.
"""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

SKEL = Path("/usr/lib/dsp/cdsp/libQnnHtpV75Skel.so")
DSP_ROOT = Path("/usr/lib/dsp")
HOST_LIBS = {
    "htp_host": Path("/usr/lib/libQnnHtp.so"),
    "htp_v75_stub": Path("/usr/lib/libQnnHtpV75Stub.so"),
}
ALLOWED_PACKAGES = frozenset(("qairt-dsp-binaries", "qairt-libs"))
MAX_OUTPUT = 8192
TRUSTED_VENDOR_ROOTS = {
    "usr_lib_dsp": Path("/usr/lib/dsp"),
    "usr_lib_firmware": Path("/usr/lib/firmware"),
    "lib_firmware": Path("/lib/firmware"),
    "usr_local_lib": Path("/usr/local/lib"),
    "opt_qualcomm": Path("/opt/qualcomm"),
    "opt_qcom": Path("/opt/qcom"),
    "usr_lib_other": Path("/usr/lib"),
}


def inspect_path(path, trusted_root):
    result = {
        "kind": "unknown",
        "resolved_regular_file": False,
        "resolved_within_trusted_tree": None,
        "resolved_target_recorded": False,
    }
    try:
        info = path.lstat()
    except FileNotFoundError:
        result["kind"] = "absent"
        return result
    except OSError:
        result["kind"] = "unavailable"
        return result
    if stat.S_ISREG(info.st_mode):
        result["kind"] = "regular_file"
        result["resolved_regular_file"] = True
        result["resolved_within_trusted_tree"] = bool(
            path.is_relative_to(trusted_root)
        )
        return result
    if not stat.S_ISLNK(info.st_mode):
        result["kind"] = "unexpected_file_type"
        return result
    result["kind"] = "symlink"
    try:
        actual = path.resolve(strict=True)  # metadata resolution, no file reads
        root = trusted_root.resolve(strict=True)
        target_stat = actual.lstat()
        result["resolved_within_trusted_tree"] = actual.is_relative_to(root)
        result["resolved_regular_file"] = stat.S_ISREG(target_stat.st_mode)
    except (OSError, RuntimeError):
        result["kind"] = "symlink_dangling_or_unavailable"
    return result


def classify_resolved_location(link, roots=TRUSTED_VENDOR_ROOTS):
    """Reveal only a known broad vendor root, never the real link target."""
    try:
        target = link.resolve(strict=True)
        if not stat.S_ISREG(target.lstat().st_mode):
            return "not_regular", None
    except (OSError, RuntimeError):
        return "unavailable", None
    for name, root in roots.items():
        try:
            real_root = root.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if target.is_relative_to(real_root):
            return name, target
    return "outside_sampled_system_roots", None


def package_owner(path):
    """Only categorize installed dpkg package ownership for the known path."""
    executable = shutil.which("dpkg-query")
    if not executable:
        return "dpkg_unavailable"
    try:
        completed = subprocess.run(
            [executable, "-S", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    data = completed.stdout
    if completed.returncode != 0 or len(data) > MAX_OUTPUT:
        return "unverified"
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError:
        return "unverified"
    # Do not use any path or unexpected package text from the response.
    if len(lines) != 1:
        return "unverified"
    prefix, sep, _ = lines[0].partition(": ")
    if not sep:
        return "unverified"
    if prefix in ALLOWED_PACKAGES:
        return prefix
    return "different_or_qualified_package"


def report():
    dsp = inspect_path(SKEL, DSP_ROOT)
    host = {
        key: inspect_path(path, Path("/usr/lib"))
        for key, path in HOST_LIBS.items()
    }
    target_region, resolved_target = classify_resolved_location(SKEL)
    owners = {
        "v75_skel_symlink": package_owner(SKEL),
        "v75_skel_resolved_file": (
            package_owner(resolved_target) if resolved_target is not None
            else "not_queried_outside_allowlist"
        ),
        **{key: package_owner(path) for key, path in HOST_LIBS.items()},
    }
    return {
        "probe": "ventuno_htp_v75_skel_symlink_package_identity_only",
        "v75_skel": dsp,
        "v75_skel_resolved_target_region": target_region,
        "host_libraries": host,
        "dpkg_owners": owners,
        "v75_skel_regular_file_in_vendor_dsp_tree": (
            dsp["resolved_regular_file"] and
            dsp["resolved_within_trusted_tree"] is True
        ),
        "stub_skel_version_compatibility_proven": False,
        "signed_unsigned_pd_policy_verified": False,
        "firmware_dsp_compatibility_proven": False,
        "raw_paths_or_links_exported": False,
        "device_or_library_opened": False,
        "qnn_htp_inference_attempted": False,
        "production_modified": False,
    }


if __name__ == "__main__":
    print("MYAI_V75_SKEL_IDENTITY_JSON=" + json.dumps(report(), sort_keys=True))
