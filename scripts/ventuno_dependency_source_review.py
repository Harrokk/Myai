"""Independent source-only dependency requirements review.

This checks manifest syntax, the known patched HTTP dependency floors and the
existing ARM64 voice source lock. It DOES NOT query PyPI, resolve transitive
dependencies, execute installers or attest the installed VENTUNO environment.
A green policy check cannot authorize deployment without a complete pinned
dependency graph, vulnerability scan, native ABI and license review.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from scripts import ventuno_voice_static_lock_check as voice_lock

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = (
    "requirements.txt",
    "requirements-ventuno.txt",
    "requirements-voice.txt",
    "requirements-bluetooth.txt",
    "requirements-camera.txt",
    "requirements-excel.txt",
    "requirements-gps.txt",
)
REQUIREMENT = re.compile(
    r"^([a-zA-Z][a-zA-Z0-9_.-]*)\s*(.*)$"
)
MIN_PATCHED = {"requests": (2, 33, 0), "urllib3": (2, 8, 0)}


def _parse_version(value):
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        return None
    return tuple(int(part or "0") for part in match.groups())


def _version_floor(spec):
    minimum = None
    for segment in spec.split(","):
        match = re.fullmatch(r"\s*(>=|==)\s*(\d+(?:\.\d+){0,2})\s*", segment)
        if match:
            version = _parse_version(match.group(2))
            if minimum is None or version > minimum:
                minimum = version
    return minimum



def _consistent_specifiers(spec):
    """Reject contradictory or unparseable simple PEP 440 numeric intervals.

    This is a narrow fail-closed SOURCE policy, not a pip resolver. Non-numeric
    versions, wildcards, compatible-release, environment markers and direct
    URLs remain unsupported rather than being assumed safe.
    """
    lower = None
    upper = None
    exact = None
    denied = set()
    for segment in spec.split(","):
        match = re.fullmatch(
            r"\s*(==|!=|>=|<=|>|<)\s*(\d+(?:\.\d+){0,2})\s*",
            segment,
        )
        if not match:
            return False
        op, version_string = match.groups()
        version = _parse_version(version_string)
        if op == "==":
            if exact is not None and exact != version:
                return False
            exact = version
        elif op == "!=":
            denied.add(version)
        elif op in (">", ">="):
            inclusive = op == ">="
            if (lower is None or version > lower[0]
                    or (version == lower[0] and not inclusive)):
                lower = (version, inclusive)
        elif op in ("<", "<="):
            inclusive = op == "<="
            if (upper is None or version < upper[0]
                    or (version == upper[0] and not inclusive)):
                upper = (version, inclusive)

    if lower and upper and (
        lower[0] > upper[0]
        or (lower[0] == upper[0]
            and (not lower[1] or not upper[1]
                 or lower[0] in denied))
    ):
        return False
    if exact is not None:
        if exact in denied:
            return False
        if lower and (exact < lower[0]
                      or (exact == lower[0] and not lower[1])):
            return False
        if upper and (exact > upper[0]
                      or (exact == upper[0] and not upper[1])):
            return False
    return True


def inspect(root=ROOT):
    root = Path(root)
    all_dependencies = {}
    valid = True
    interval_count = 0
    no_hash_count = 0
    for name in REQUIREMENTS:
        path = root / name
        found = []
        try:
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < 32768:
                raise ValueError("missing-symlink-or-oversize")
            for row in path.read_text(encoding="utf-8").splitlines():
                value = row.split("#", 1)[0].strip()
                if not value:
                    continue
                m = REQUIREMENT.fullmatch(value)
                if not m or not re.fullmatch(r"(?:[<>=!~.,0-9 ]+)", m.group(2)):
                    raise ValueError("untrusted-dependency-directive")
                package = re.sub(r"[-_.]+", "-", m.group(1)).lower()
                if package in [entry["name"] for entry in found]:
                    raise ValueError("duplicate-dependency")
                spec = m.group(2).strip()
                if not spec or not _consistent_specifiers(spec):
                    raise ValueError("invalid-or-contradictory-dependency-interval")
                found.append({"name": package, "specifier": spec})
                no_hash_count += 1
                interval_count += int("==" not in spec)
        except (OSError, UnicodeError, ValueError):
            valid = False
        all_dependencies[name] = found
    root_pins = {x["name"]: x["specifier"] for x in all_dependencies["requirements.txt"]}
    floors = {
        key: _version_floor(root_pins.get(key, ""))
        for key in MIN_PATCHED
    }
    secure_http_floor = all(
        floors.get(key) is not None and floors[key] >= patched
        for key, patched in MIN_PATCHED.items()
    )
    voice = voice_lock.inspect(root)
    complete = valid and secure_http_floor and voice["source_lock_consistent"]
    return {
        "status": ("source-dependency-policy-checked-release-unlocked" if complete
                   else "blocked-source-dependency-policy"),
        "requirements_files_reviewed": len(REQUIREMENTS),
        "direct_requirements": sum(map(len, all_dependencies.values())),
        "version_range_requirements": interval_count,
        "direct_requirements_without_hashes": no_hash_count,
        "package_groups": {key: len(value) for key, value in all_dependencies.items()},
        "patched_http_minimums": secure_http_floor,
        "hashed_arm64_voice_wheels": voice["pinned_wheel_records"],
        "hashed_arm64_voice_source_lock_consistent": voice["source_lock_consistent"],
        "source_policy_checked": complete,
        "advisory_database_live_queried": False,
        "transitive_dependency_security_checked": False,
        "installed_versions_examined": False,
        "installed_native_abi_verified": False,
        "licenses_verified": False,
        "production_dependency_lock_complete": False,
        "production_install_authorized": False,
    }


def main():
    report = inspect()
    print("MYAI_DEPENDENCY_SOURCE_REVIEW_JSON=" + json.dumps(report, sort_keys=True))
    return 0 if report["source_policy_checked"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
