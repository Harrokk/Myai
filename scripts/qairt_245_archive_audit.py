"""Offline bounded inspection of the official QAIRT 2.45 SDK ZIP archive.

Do NOT execute, extract, redistribute or upload vendor programs. Report
only aggregate ZIP metadata and allowlisted host conversion component names.
The archive is acquired by a separate ephemeral GitHub-hosted workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

MAX_ARCHIVE_BYTES = 2_900_000_000
MAX_ENTRY_COUNT = 90_000
MAX_UNCOMPRESSED_BYTES = 11_000_000_000
MAX_INDIVIDUAL_BYTES = 2_000_000_000
EXPECTED_RELEASE = "2.45.0.260326"
EXPECTED_COMPONENTS = (
    "qnn-onnx-converter",
    "qnn-model-lib-generator",
    "qnn-context-binary-generator",
    "libQnnHtp.so",
    "libQnnModelDlc.so",
)
HOST_TOOLS = frozenset(EXPECTED_COMPONENTS[:2])


def safe_zip_member(name: str) -> bool:
    if not name or len(name) > 1024 or "\\" in name:
        return False
    path = PurePosixPath(name)
    return (not path.is_absolute() and
            ".." not in path.parts and
            all(part not in ("", ".") for part in path.parts))


def component_label(member: str) -> str | None:
    parts = PurePosixPath(member).parts
    if len(parts) < 3:
        return None
    basename = parts[-1]
    if basename in HOST_TOOLS or basename in {
        name + ".py" for name in HOST_TOOLS
    }:
        if "bin" in parts and "x86_64-linux-clang" in parts:
            return basename.split(".py")[0]
    if basename in ("libQnnHtp.so", "libQnnModelDlc.so"):
        if "lib" in parts:
            return basename
    if basename == "qnn-context-binary-generator":
        if "bin" in parts and "x86_64-linux-clang" in parts:
            return basename
    return None


def inspect_archive(path: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "inconclusive-archive-unavailable",
        "expected_qairt_release": EXPECTED_RELEASE,
        "archive_sha256": None,
        "compressed_bytes": 0,
        "entry_count": 0,
        "uncompressed_bytes": 0,
        "components_present": [],
        "path_traversal_entries_present": False,
        "symlink_entries_present": False,
        "sdk_extracted": False,
        "sdk_binaries_executed": False,
        "qnn_model_converted": False,
        "target_htp_profile_measured": False,
        "production_services_changed": False,
    }
    if not path.is_file() or path.is_symlink():
        return report
    size = path.stat().st_size
    report["compressed_bytes"] = size
    if size <= 0 or size > MAX_ARCHIVE_BYTES:
        report["status"] = "reject-archive-size"
        return report
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    report["archive_sha256"] = digest.hexdigest()
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            report["entry_count"] = len(entries)
            if len(entries) > MAX_ENTRY_COUNT:
                report["status"] = "reject-too-many-zip-entries"
                return report
            found: set[str] = set()
            cumulative = 0
            for entry in entries:
                if not safe_zip_member(entry.filename):
                    report["path_traversal_entries_present"] = True
                if stat.S_ISLNK((entry.external_attr >> 16) & 0xFFFF):
                    report["symlink_entries_present"] = True
                if entry.file_size > MAX_INDIVIDUAL_BYTES:
                    report["status"] = "reject-huge-uncompressed-entry"
                    return report
                cumulative += entry.file_size
                if cumulative > MAX_UNCOMPRESSED_BYTES:
                    report["status"] = "reject-unbounded-zip-expansion"
                    return report
                label = component_label(entry.filename)
                if label:
                    found.add(label)
            report["uncompressed_bytes"] = cumulative
            report["components_present"] = sorted(found)
            if report["path_traversal_entries_present"] or report["symlink_entries_present"]:
                report["status"] = "reject-unsafe-zip-paths"
            elif not set(EXPECTED_COMPONENTS[:2]).issubset(found):
                report["status"] = "inconclusive-required-converters-not-found"
            else:
                report["status"] = "host-conversion-components-in-official-archive"
    except (OSError, BadZipFile, ValueError):
        report["status"] = "reject-invalid-zip-file"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_archive(args.zip)
    print("Bounded QAIRT 2.45 official archive inventory:",
          json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "host-conversion-components-in-official-archive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
