"""Bounded, read-only evidence of VENTUNO's installed Python packages.

No module import, package install, socket, service, model, mic or NPU is used.
Only allowlisted distribution names, installed versions and aggregate counts
are reported. A successful inventory never authorizes production release.
"""
from __future__ import annotations

import importlib.metadata as metadata
import json
import re

TRACKED = (
    "requests", "urllib3", "psutil", "arduino-router-bridge",
    "faster-whisper", "av", "ctranslate2", "sounddevice",
    "webrtcvad-wheels", "pyttsx3", "openpyxl", "bleak",
    "opencv-python-headless", "pyserial",
)
CRITICAL_FLOORS = {
    "requests": (2, 33, 0),
    "urllib3": (2, 8, 0),
}


def _version_tuple(s):
    if not isinstance(s, str):
        return None
    # No custom plugin/package imports. Pre-releases are not attested as
    # security-patched releases by this diagnostic.
    m = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", s)
    if not m:
        return None
    return tuple(int(part or 0) for part in m.groups())


def observe(*, lookup=None, package_count=None):
    if lookup is None:
        lookup = metadata.version
    if package_count is None:
        # Names, locations, home directories and dependency metadata are
        # deliberately not included in printed output.
        try:
            package_count = sum(1 for _ in metadata.distributions())
        except (OSError, ValueError):
            package_count = None
    found = {}
    for package in TRACKED:
        try:
            value = lookup(package)
            value = str(value)
            # Avoid logging unexpected private metadata or arbitrary paths.
            if not re.fullmatch(r"[A-Za-z0-9_.+!-]{1,64}", value):
                value = "unverified-version-metadata"
        except metadata.PackageNotFoundError:
            value = None
        except (OSError, ValueError, TypeError):
            value = "unverified-version-metadata"
        found[package] = value
    patched = {}
    for name, floor in CRITICAL_FLOORS.items():
        observed = _version_tuple(found[name])
        patched[name] = observed is not None and observed >= floor
    voice_names = ("faster-whisper", "sounddevice", "webrtcvad-wheels", "pyttsx3")
    return {
        "status": "read-only-installed-dependency-inventory",
        "known_package_count": len(TRACKED),
        "environment_distribution_count": package_count,
        "allowlisted_installed_versions": found,
        "patched_network_dependency_floors_observed": patched,
        "network_dependency_policy_observed": all(patched.values()),
        "usual_voice_package_count": sum(
            found[n] is not None and found[n] != "unverified-version-metadata"
            for n in voice_names
        ),
        "active_system_configuration_verified": False,
        "all_transitive_dependencies_resolved": False,
        "os_and_native_libraries_verified": False,
        "licenses_verified": False,
        "external_advisories_live_checked": False,
        "packages_installed_or_modified": False,
        "physical_hardware_test_performed": False,
        "production_deployment_authorized": False,
    }


def main():
    report = observe()
    print("MYAI_INSTALLED_DEPENDENCY_READONLY_JSON=" + json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "read-only-installed-dependency-inventory" else 2


if __name__ == "__main__":
    raise SystemExit(main())
