"""Read-only VENTUNO Q QAIRT / HTP-v75 packaging inventory.

Only whitelisted dpkg-query status/version reads and lstat metadata from
exact vendor-documented paths; no loading any QNN or DSP library, no model
execution, no device opens, no environment dump, no sensitive paths printed.
Absence at sampled paths does not prove the library is absent globally.
"""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

PACKAGE_NAMES = (
    "qairt-libs",
    "qairt-dsp-binaries",
    "qnn-tools",
    "libqnn1",
    "libqnn-dev",
)
LIBRARY_LOCATIONS = {
    "usr_lib": Path("/usr/lib"),
    "usr_lib_dsp_cdsp": Path("/usr/lib/dsp/cdsp"),
    "usr_lib_rfsa_adsp": Path("/usr/lib/rfsa/adsp"),
    "geniex_qairt": Path("/home/arduino/.local/share/geniex/qairt"),
}
FILE_NAMES = (
    "libQnnHtp.so",
    "libQnnHtpV75Stub.so",
    "libQnnHtpV75Skel.so",
    "libQnnModelDlc.so",
    "libQnnCpu.so",
    "libQnnTFLiteDelegate.so",
    "libcdsprpc.so",
)
VERSION_RE = re.compile(r"^[A-Za-z0-9.+:~_-]{1,64}$")
MAX_OUTPUT_BYTES = 128


def classify_package_output(returncode, output):
    """Accept only a literal installed-status marker and bounded version."""
    if returncode != 0 or type(output) is not bytes:
        return {"status": "unavailable", "version": None}
    if len(output) > MAX_OUTPUT_BYTES:
        return {"status": "unavailable", "version": None}
    try:
        left, version = output.decode("ascii").strip().split("|", 1)
    except (ValueError, UnicodeError):
        return {"status": "unavailable", "version": None}
    if left.strip() == "ii" and VERSION_RE.fullmatch(version):
        return {"status": "installed", "version": version}
    return {"status": "not_installed_or_unverified", "version": None}


def package_versions():
    tool = shutil.which("dpkg-query")
    if not tool:
        return {name: {"status": "tool_unavailable", "version": None}
                for name in PACKAGE_NAMES}
    results = {}
    for name in PACKAGE_NAMES:
        try:
            completed = subprocess.run(
                [tool, "-W", "-f=${db:Status-Abbrev}|${Version}", name],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                check=False, timeout=5, env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            )
            results[name] = classify_package_output(
                completed.returncode, completed.stdout
            )
        except (OSError, subprocess.TimeoutExpired):
            results[name] = {"status": "unavailable", "version": None}
    return results


def sampled_artifacts(roots=LIBRARY_LOCATIONS):
    """Enumerate ONLY 28 known candidate path pairs using lstat, not open."""
    result = {}
    for key, folder in roots.items():
        result[key] = {}
        for filename in FILE_NAMES:
            path = folder / filename
            try:
                value = path.lstat()
            except FileNotFoundError:
                kind = "absent"
            except OSError:
                kind = "unreadable"
            else:
                if stat.S_ISREG(value.st_mode):
                    kind = "regular_file"
                elif stat.S_ISLNK(value.st_mode):
                    kind = "symlink_unresolved"
                else:
                    kind = "unexpected_type"
            result[key][filename] = kind
    return result


def summarize(packages=None, libraries=None):
    packages = package_versions() if packages is None else packages
    libraries = sampled_artifacts() if libraries is None else libraries
    # Summarize presence separately from exact candidate locations.
    v75 = [
        libraries.get(root, {}).get("libQnnHtpV75Skel.so")
        for root in LIBRARY_LOCATIONS
    ]
    htp = [libraries.get(root, {}).get("libQnnHtp.so")
           for root in LIBRARY_LOCATIONS]
    def present(samples):
        return any(x in ("regular_file", "symlink_unresolved") for x in samples)
    return {
        "probe": "ventuno_qairt_v75_package_metadata_only",
        "packages": packages,
        "sampled_files": libraries,
        "v75_skel_in_sampled_paths": present(v75),
        "htp_host_lib_in_sampled_paths": present(htp),
        "arduino_documented_qairt_packages_installed": all(
            packages.get(name, {}).get("status") == "installed"
            for name in ("qairt-libs", "qairt-dsp-binaries")
        ),
        "installed_runtime_matches_synthetic_dlc_sdk_proven": False,
        "dsp_host_firmware_compatibility_proven": False,
        "dsp_process_domain_policy_verified": False,
        "files_or_devices_opened": False,
        "qnn_or_htp_executed": False,
        "software_installed_or_modified": False,
    }


if __name__ == "__main__":
    print("MYAI_QAIRT_V75_PACKAGE_METADATA_JSON=" +
          json.dumps(summarize(), sort_keys=True))
