"""Offline validation of a future *reviewed* ARM64 voice wheelhouse.

No pip call, download, installation, native import, audio, NPU or files
written. A missing manifest intentionally yields a blocked result.
Only local JSON and file metadata under a caller-supplied, private folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

REQUIRED = ("faster_whisper", "sounddevice", "webrtcvad_wheels", "pyttsx3")
WHEEL_NAME = re.compile(
    r"(?P<name>[A-Za-z0-9_.]+)-(?P<version>[0-9][A-Za-z0-9_.!+\-]*)-"
    r"(?P<py>[A-Za-z0-9_.]+)-(?P<abi>[A-Za-z0-9_.]+)-"
    r"(?P<plat>[A-Za-z0-9_.]+)\.whl\Z"
)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_MANIFEST = 32768
MAX_WHEEL = 250_000_000
MAX_FILES = 100


def _normalize(value):
    return value.lower().replace("-", "_").replace(".", "_")


def _compatible(filename):
    match = WHEEL_NAME.fullmatch(filename)
    if match is None:
        return None
    data = match.groupdict()
    python_tag, abi, platform_tag = (
        data["py"], data["abi"], data["plat"]
    )
    abi_tags = set(abi.split("."))
    # CPython limited ABI3 wheels built for older Python versions remain
    # valid on CPython 3.12. E.g. cp38-abi3, cp310-abi3; cp313 is not.
    abi3 = "abi3" in abi_tags
    python_ok = any(
        tag in {"cp312", "py3", "py312"}
        or (abi3 and tag.startswith("cp3") and
            tag[3:].isdigit() and 7 <= int(tag[3:]) <= 12)
        for tag in python_tag.split(".")
    )
    abi_ok = bool(abi_tags & {"none", "abi3", "cp312"})
    platform_ok = any(
        tag == "any"
        or tag == "linux_aarch64"
        or re.fullmatch(r"manylinux(?:2014|_2_(?:17|[1-3]\d))_aarch64", tag)
        for tag in platform_tag.split(".")
    )
    return data if python_ok and abi_ok and platform_ok else None


def classify(directory):
    result = {
        "status": "blocked-no-reviewed-wheelhouse",
        "reviewed_packages": 0,
        "required_packages": len(REQUIRED),
        "wheel_file_hashes_verified": False,
        "all_wheels_arm64_py312_compatible_by_filename": False,
        "dependency_closure_verified": False,
        "wheelhouse_installed": False,
        "package_download_attempted": False,
        "native_abi_tested": False,
        "audio_authorized": False,
        "npu_tested": False,
    }
    if directory is None:
        return result
    directory = Path(directory)
    manifest = directory / "wheelhouse.lock.json"
    try:
        if directory.is_symlink() or not directory.is_dir():
            return result
        if (manifest.is_symlink() or not manifest.is_file()
                or not 0 < manifest.stat().st_size <= MAX_MANIFEST):
            return result
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if (not isinstance(data, dict)
                or data.get("python") != "cp312"
                or data.get("platform") != "aarch64"
                or data.get("complete_dependency_closure") is not True
                or not isinstance(data.get("wheels"), list)):
            return result
        rows = data["wheels"]
        if not 4 <= len(rows) <= MAX_FILES:
            return result
        names = set()
        valid = True
        for item in rows:
            if (not isinstance(item, dict)
                    or set(item) != {"filename", "sha256"}):
                valid = False
                break
            name, digest = item["filename"], item["sha256"]
            if not (type(name) is str and type(digest) is str
                    and HEX64.fullmatch(digest)):
                valid = False
                break
            parsed = _compatible(name)
            if parsed is None or "/" in name or "\\" in name:
                valid = False
                break
            normalized = _normalize(parsed["name"])
            if normalized in names:
                valid = False
                break
            names.add(normalized)
            path = directory / name
            if (path.is_symlink() or not path.is_file()
                    or not 0 < path.stat().st_size <= MAX_WHEEL):
                valid = False
                break
            checksum = hashlib.sha256()
            with path.open("rb") as stream:
                while True:
                    block = stream.read(65536)
                    if not block:
                        break
                    checksum.update(block)
            if checksum.hexdigest() != digest:
                valid = False
                break
        if valid:
            result["reviewed_packages"] = len(names & set(REQUIRED))
        if valid and set(REQUIRED).issubset(names):
            result["status"] = "reviewed-wheelhouse-hashes-and-tags-only"
            result["wheel_file_hashes_verified"] = True
            result["all_wheels_arm64_py312_compatible_by_filename"] = True
            # Manifest alone cannot establish transitive dependency resolution.
            # Requires separately reviewed metadata/ABI and native imports.
            result["dependency_closure_verified"] = False
    except (OSError, ValueError, TypeError, UnicodeError):
        pass
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args(argv)
    print("MYAI_VOICE_WHEELHOUSE_GATE_JSON=" +
          json.dumps(classify(args.wheelhouse), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
