"""Offline examination of a MINIMAL normalized Qualcomm get_frameworks snapshot.

A snapshot is *not* an authenticated live catalogue. It is never enough
to authorize model uploads, job submission, or HTP execution. Do not pass
credentials or raw CLI output: input is a strictly structured list of
public Framework(name, api_version, full_version, api_tags) fields.
No qai_hub import, network, package install or proprietary SDK.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat

MAX_SNAPSHOT_BYTES = 16_384
MAX_ENTRIES = 64
EXPECTED_MINOR = "2.46"
FIELDS = frozenset({"name", "api_version", "full_version", "api_tags"})
NAME_RE = re.compile(r"^[A-Za-z0-9_.+-]{1,32}$")
API_VERSION_RE = re.compile(r"^[0-9]{1,3}\.[0-9]{1,3}$")
FULL_VERSION_RE = re.compile(r"^[0-9]{1,3}(?:\.[0-9]{1,12}){2,4}$")
TAG_RE = re.compile(r"^[a-z]{1,24}$")


def blank_report():
    return {
        "probe": "ventuno_qai_hub_qairstack_catalog_snapshot_readonly",
        "status": "no_go_catalog_snapshot_not_supplied",
        "normalized_snapshot_schema_valid": False,
        "qairt_246_in_supplied_snapshot": None,
        "qairt_246_full_version_pattern_consistent": None,
        "record_count": 0,
        "catalog_live_authenticity_verified": False,
        "catalog_freshness_verified": False,
        "exact_ventuno_target_support_for_246_verified": False,
        "model_graph_or_operator_compatibility_verified": False,
        "cloud_request_performed": False,
        "api_credentials_accessed": False,
        "model_uploaded": False,
        "compile_or_link_job_submitted": False,
        "npu_executed": False,
        "production_modified": False,
        "raw_catalog_entries_or_file_paths_exported": False,
    }


def reject_duplicate_json_keys(pairs):
    obj = {}
    for k, value in pairs:
        if k in obj:
            raise ValueError("duplicate-json-key")
        obj[k] = value
    return obj


def inspect_snapshot_bytes(data: bytes):
    report = blank_report()
    if type(data) is not bytes or not 2 <= len(data) <= MAX_SNAPSHOT_BYTES:
        report["status"] = "no_go_invalid_snapshot_length"
        return report
    try:
        payload = json.loads(data.decode("utf-8"),
                             object_pairs_hook=reject_duplicate_json_keys)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        report["status"] = "no_go_unparseable_or_duplicate_json"
        return report
    if (type(payload) is not dict
            or set(payload) != {"frameworks"}
            or type(payload["frameworks"]) is not list
            or not 1 <= len(payload["frameworks"]) <= MAX_ENTRIES):
        report["status"] = "no_go_invalid_snapshot_schema"
        return report

    qairt_matches = []
    for record in payload["frameworks"]:
        if type(record) is not dict or set(record) != FIELDS:
            report["status"] = "no_go_invalid_framework_record"
            return report
        name = record["name"]
        version = record["api_version"]
        full = record["full_version"]
        tags = record["api_tags"]
        if (type(name) is not str or not NAME_RE.fullmatch(name)
                or type(version) is not str or not API_VERSION_RE.fullmatch(version)
                or type(full) is not str or not FULL_VERSION_RE.fullmatch(full)
                or type(tags) is not list or len(tags) > 8
                or any(type(tag) is not str or not TAG_RE.fullmatch(tag)
                       for tag in tags)
                or len(set(tags)) != len(tags)):
            report["status"] = "no_go_invalid_framework_value"
            return report
        if name == "QAIRT" and version == EXPECTED_MINOR:
            qairt_matches.append(full)

    report["normalized_snapshot_schema_valid"] = True
    report["record_count"] = len(payload["frameworks"])
    if len(qairt_matches) > 1:
        report["status"] = "no_go_ambiguous_duplicate_qairt_246_versions"
        report["qairt_246_in_supplied_snapshot"] = None
    elif len(qairt_matches) == 1:
        report["qairt_246_in_supplied_snapshot"] = True
        report["qairt_246_full_version_pattern_consistent"] = (
            qairt_matches[0].startswith(EXPECTED_MINOR + ".")
        )
        report["status"] = (
            "snapshot_lists_246_live_availability_unverified"
            if report["qairt_246_full_version_pattern_consistent"]
            else "no_go_framework_version_inconsistency"
        )
    else:
        report["qairt_246_in_supplied_snapshot"] = False
        report["status"] = "snapshot_does_not_list_246_not_live_proof"
    return report


def inspect_snapshot_file(path: Path | None):
    if path is None:
        return blank_report()
    output = blank_report()
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 2 <= before.st_size <= MAX_SNAPSHOT_BYTES:
            output["status"] = "no_go_untrusted_snapshot_file"
            return output
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        flags |= getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        try:
            after = os.fstat(fd)
            if (not stat.S_ISREG(after.st_mode)
                    or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
                    or not 2 <= after.st_size <= MAX_SNAPSHOT_BYTES):
                output["status"] = "no_go_snapshot_changed_or_untrusted"
                return output
            data = os.read(fd, MAX_SNAPSHOT_BYTES + 1)
        finally:
            os.close(fd)
        return inspect_snapshot_bytes(data)
    except OSError:
        output["status"] = "no_go_snapshot_file_unavailable"
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized-frameworks-json", type=Path,
                        default=None)
    args = parser.parse_args()
    print("MYAI_QAIRT_CATALOG_SNAPSHOT_JSON=" + json.dumps(
        inspect_snapshot_file(args.normalized_frameworks_json),
        sort_keys=True
    ))
    # A reported snapshot is never license to run cloud jobs.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
