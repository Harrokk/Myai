"""Bounded package provenance for the named CDSP firmware and DSP shell.

No firmware payload/header is opened. Only stat, exact-path dpkg-query -S,
and optionally dpkg-query -W for a SMALL allowlist of vendor package names.
Nothing prints raw firmware names, paths, package tool logs, IDs or versions
except allowlisted packages. Ownership never proves loaded firmware identity.
"""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

from scripts.ventuno_cdsp_firmware_search_readonly import (
    cdsp_entry, verified_firmware_name, FIRMWARE_ROOT, MAX_FIRMWARE_NAME,
    SAFE_COMPONENT,
)
from scripts.ventuno_cdsp_remoteproc_shell_readonly import small_attr
from scripts.ventuno_v75_elf_fastrpc_readonly import (
    classify_package_output,
)

KNOWN_PACKAGE_FAMILIES = {
    "qairt-dsp-binaries": "qairt_dsp_binaries",
    "qairt-libs": "qairt_host_libraries",
    "qcom-fastrpc1": "qcom_fastrpc",
    "firmware-qcom-soc": "qcom_firmware",
    "linux-firmware": "linux_firmware",
    "qcom-firmware": "qcom_firmware",
}
PACKAGE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,90}(?::[a-z0-9-]{1,24})?$")
SHELL = Path("/usr/lib/dsp/cdsp/fastrpc_shell_unsigned_3")
USR_ROOT = Path("/usr")
MAX_SEARCH_CANDIDATES = 4
MAX_DPKG_STDOUT = 8192


def parse_owner_record(raw, expected_path):
    """Require one literal matching dpkg owner line; discard all raw text."""
    if not isinstance(raw, bytes) or len(raw) > MAX_DPKG_STDOUT:
        return "unverified", None
    try:
        lines = raw.decode("utf-8").strip().splitlines()
    except UnicodeError:
        return "unverified", None
    if len(lines) != 1:
        return "unverified", None
    owner, separator, listed = lines[0].partition(": ")
    if not separator or listed != str(expected_path):
        return "unverified", None
    if not PACKAGE_TOKEN.fullmatch(owner):
        return "unverified", None
    name = owner.split(":")[0]
    if name in KNOWN_PACKAGE_FAMILIES:
        return "allowlisted_package", name
    return "other_dpkg_package", None


def dpkg_owner(path, tool=None):
    tool = shutil.which("dpkg-query") if tool is None else tool
    if tool is None:
        return "dpkg_unavailable", None
    try:
        result = subprocess.run(
            [tool, "-S", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=5,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return "query_unavailable", None
    if result.returncode == 1:
        return "not_listed_in_dpkg", None
    if result.returncode != 0:
        return "query_unavailable", None
    return parse_owner_record(result.stdout, path)


def package_version(name, tool=None):
    if name not in KNOWN_PACKAGE_FAMILIES:
        return None
    tool = shutil.which("dpkg-query") if tool is None else tool
    if tool is None:
        return None
    try:
        result = subprocess.run(
            [tool, "-W", "-f=" + "$" + "{db:Status-Abbrev}|" +
             "$" + "{Version}", name],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=5,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    parsed = classify_package_output(result.returncode, result.stdout)
    return parsed["version"] if parsed["status"] == "installed" else None


def candidates(name, root=FIRMWARE_ROOT, release=None):
    """Enumerate only documented firmware request paths, with strict bound."""
    try:
        real_root = root.resolve(strict=True)
        if not real_root.is_dir():
            return []
    except (OSError, RuntimeError):
        return []
    release = os.uname().release if release is None else release
    prefixes = [("updates",), ()]
    if SAFE_COMPONENT.fullmatch(release):
        prefixes = [("updates", release), ("updates",),
                    (release,), ()]
    results = []
    for prefix in prefixes[:MAX_SEARCH_CANDIDATES]:
        candidate = root.joinpath(*prefix, *name)
        try:
            target = candidate.resolve(strict=True)
            if not target.is_relative_to(real_root):
                continue
            metadata = target.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                continue
        except (OSError, RuntimeError):
            continue
        results.append((candidate, target))
    return results


def file_provenance(candidate, target):
    """Try packaged symlink name and resolved file; avoid false negatives."""
    initial, first_owner = dpkg_owner(candidate)
    if first_owner:
        result_status, pkg = initial, first_owner
    else:
        result_status, pkg = dpkg_owner(target)
        if not pkg and result_status == "not_listed_in_dpkg":
            # Dpkg may not own either spelling. Not proof of tampering.
            result_status = "not_listed_in_sampled_dpkg_paths"
    if pkg:
        return {"status": result_status,
                "package_family": KNOWN_PACKAGE_FAMILIES[pkg],
                "package_version": package_version(pkg)}
    return {"status": result_status,
            "package_family": None, "package_version": None}


def report(remote_root=None, firmware_root=FIRMWARE_ROOT, shell=SHELL):
    classification, node = (cdsp_entry() if remote_root is None
                             else cdsp_entry(remote_root))
    outcome = {
        "probe": "ventuno_cdsp_dpkg_firmware_shell_provenance_only",
        "running_cdsp_identified": classification == "one_running_cdsp",
        "firmware_name_usable": False,
        "regular_firmware_candidates_examined": 0,
        "firmware_package_provenance": "not_checked",
        "firmware_package_family": None,
        "firmware_package_version": None,
        "multiple_firmware_candidate_packages": False,
        "shell_target": "unavailable",
        "shell_package_provenance": "not_checked",
        "shell_package_family": None,
        "shell_package_version": None,
        "matching_firmware_build_and_shell_verified": False,
        "running_firmware_binary_verified": False,
        "signed_or_unsigned_pd_verified": False,
        "firmware_payload_read": False,
        "device_opened": False,
        "qnn_or_htp_executed": False,
        "production_modified": False,
        "raw_names_paths_or_dpkg_logs_exported": False,
    }
    if node is not None:
        name = verified_firmware_name(small_attr(
            node / "firmware", MAX_FIRMWARE_NAME))
        if name is not None:
            outcome["firmware_name_usable"] = True
            paths = candidates(name, firmware_root)
            outcome["regular_firmware_candidates_examined"] = len(paths)
            records = [file_provenance(c, t) for c, t in paths]
            owners = {(x["status"], x["package_family"],
                       x["package_version"]) for x in records}
            if len(owners) == 1:
                entry = records[0]
                outcome["firmware_package_provenance"] = entry["status"]
                outcome["firmware_package_family"] = entry["package_family"]
                outcome["firmware_package_version"] = entry["package_version"]
            elif len(owners) > 1:
                outcome["multiple_firmware_candidate_packages"] = True
                outcome["firmware_package_provenance"] = "ambiguous_candidates"
            else:
                outcome["firmware_package_provenance"] = "no_regular_candidates"
    try:
        target = shell.resolve(strict=True)
        root = USR_ROOT.resolve(strict=True)
        if target.is_relative_to(root) and stat.S_ISREG(target.lstat().st_mode):
            outcome["shell_target"] = "regular_file_under_usr"
            owner = file_provenance(shell, target)
            outcome["shell_package_provenance"] = owner["status"]
            outcome["shell_package_family"] = owner["package_family"]
            outcome["shell_package_version"] = owner["package_version"]
        else:
            outcome["shell_target"] = "outside_scope_or_nonregular"
    except (OSError, RuntimeError):
        pass
    return outcome


if __name__ == "__main__":
    print("MYAI_CDSP_PACKAGE_PROVENANCE_JSON=" + json.dumps(
        report(), sort_keys=True))
