"""Source-only consistency audit for the future ARM64 voice wheel pin set.

This does not download/execute wheels or attest native ABI. The lock files
remain inert and cannot install anything or authorize physical audio.
"""
from __future__ import annotations

import json
from pathlib import Path
from scripts.ventuno_voice_wheelhouse_gate import HEX64, REQUIRED, _compatible, _normalize

ROOT = Path(__file__).resolve().parents[1]


def inspect(root=ROOT):
    valid = False
    count = 0
    try:
        lock_path = root / "config/voice_arm64_cp312_wheels.lock.json"
        text_path = root / "requirements-voice-arm64-hashed.lock"
        if (lock_path.is_symlink() or text_path.is_symlink()
                or not lock_path.is_file() or not text_path.is_file()
                or not 0 < lock_path.stat().st_size < 33000
                or not 0 < text_path.stat().st_size < 33000):
            raise ValueError("Missing reviewed lock source")
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        wheels = lock.get("wheels")
        if (lock.get("schema") != 1 or lock.get("python") != "cp312"
                or lock.get("platform") != "aarch64"
                or lock.get("complete_dependency_closure") is not True
                or not isinstance(wheels, list) or len(wheels) != 28):
            raise ValueError("Invalid lock target/count")
        count = len(wheels)
        names, expected = set(), []
        for item in wheels:
            if not isinstance(item, dict) or set(item) != {"filename", "sha256"}:
                raise ValueError("Unknown artifact properties")
            filename, sha = item["filename"], item["sha256"]
            if not (isinstance(filename, str) and isinstance(sha, str)
                    and HEX64.fullmatch(sha)):
                raise ValueError("Missing SHA256")
            parsed = _compatible(filename)
            if parsed is None:
                raise ValueError("Incompatible wheel tag")
            name = _normalize(parsed["name"])
            if name in names:
                raise ValueError("Duplicate wheel distribution")
            names.add(name)
            expected.append(
                parsed["name"].replace("_", "-") + "==" + parsed["version"]
                + " --hash=sha256:" + sha
            )
        pinned = [
            line.strip() for line in text_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        valid = (
            set(REQUIRED).issubset(names)
            and len(expected) == len(set(expected))
            and sorted(pinned) == sorted(expected)
        )
    except (OSError, TypeError, ValueError, UnicodeError, KeyError):
        valid = False
    return {
        "status": "arm64-source-wheel-lock-coherent" if valid else "blocked-unreviewed-wheel-lock",
        "pinned_wheel_records": count,
        "source_lock_consistent": valid,
        "live_pypi_artifacts_reverified": False,
        "dependency_import_abi_verified": False,
        "model_loaded": False,
        "voice_authorized": False,
        "npu_executed": False,
        "packages_installed": False,
    }


def main():
    report = inspect()
    print("MYAI_VOICE_SOURCE_WHEEL_LOCK_JSON=" + json.dumps(report, sort_keys=True))
    return 0 if report["source_lock_consistent"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
