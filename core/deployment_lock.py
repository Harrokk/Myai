import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import shutil
import subprocess


LOCK_SCHEMA_VERSION = 2

_REQUIRED_FIELDS = (
    ("platform", "system"),
    ("platform", "machine"),
    ("platform", "python"),
    ("geniex", "version"),
    ("packages", "requests"),
    ("packages", "psutil"),
    ("files", "requirements.txt", "sha256"),
    ("files", "requirements-ventuno.txt", "sha256"),
    ("files", "requirements-bluetooth.txt", "sha256"),
    ("files", "requirements-camera.txt", "sha256"),
    ("files", "requirements-voice.txt", "sha256"),
    ("files", "requirements-gps.txt", "sha256"),
    ("models", "llm"),
)


def _default_command_runner(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _command_text(result):
    stdout = str(
        getattr(
            result,
            "stdout",
            "",
        )
        or ""
    ).strip()
    stderr = str(
        getattr(
            result,
            "stderr",
            "",
        )
        or ""
    ).strip()
    return stdout if stdout else stderr


def _distribution_version(name):
    try:
        return importlib.metadata.version(
            name
        )
    except importlib.metadata.PackageNotFoundError:
        return None


def _file_sha256(path):
    path = Path(path)

    if not path.is_file():
        return None

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(65536),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _value_at(data, path):
    current = data

    for key in path:
        if not isinstance(
            current,
            dict,
        ):
            return None
        current = current.get(
            key
        )

    return current


def _flatten(data, prefix=()):
    if not isinstance(
        data,
        dict,
    ):
        return [
            (
                prefix,
                data,
            )
        ]

    result = []

    for key, value in data.items():
        result.extend(
            _flatten(
                value,
                prefix
                + (
                    str(key),
                ),
            )
        )

    return result


def resolve_project_path(
    project_root,
    raw_path,
):
    path = Path(
        str(
            raw_path
            or ""
        )
    )

    if not path.is_absolute():
        path = (
            Path(project_root)
            / path
        )

    return path


def collect_ventuno_stack(
    settings,
    project_root,
    *,
    system=None,
    machine=None,
    python_version=None,
    which=None,
    command_runner=None,
    distribution_version=None,
):
    """Collect read-only software identifiers without inference or hardware writes."""

    which = which or shutil.which
    command_runner = (
        command_runner
        or _default_command_runner
    )
    distribution_version = (
        distribution_version
        or _distribution_version
    )

    geniex_version = None
    geniex_path = which(
        "geniex"
    )

    if geniex_path:
        try:
            result = command_runner(
                [
                    str(
                        geniex_path
                    ),
                    "--version",
                ]
            )
            if (
                getattr(
                    result,
                    "returncode",
                    1,
                )
                == 0
            ):
                text = _command_text(
                    result
                )
                geniex_version = (
                    text
                    or None
                )
        except Exception:
            geniex_version = None

    package_versions = {}

    for package_name in (
        "requests",
        "psutil",
        "bleak",
        "arduino-router-bridge",
    ):
        try:
            package_versions[
                package_name
            ] = distribution_version(
                package_name
            )
        except Exception:
            package_versions[
                package_name
            ] = None

    root = Path(
        project_root
    )
    requirement_files = (
        "requirements.txt",
        "requirements-ventuno.txt",
        "requirements-bluetooth.txt",
        "requirements-camera.txt",
        "requirements-voice.txt",
        "requirements-gps.txt",
    )
    requirement_hashes = {
        name: _file_sha256(
            root / name
        )
        for name in requirement_files
    }

    geniex = settings.get(
        "geniex",
        {},
    )
    vision = settings.get(
        "vision",
        {},
    )

    return {
        "platform": {
            "system": str(
                system
                if system is not None
                else platform.system()
            ),
            "machine": str(
                machine
                if machine is not None
                else platform.machine()
            ),
            "python": str(
                python_version
                if python_version is not None
                else platform.python_version()
            ),
        },
        "geniex": {
            "version": (
                geniex_version
            ),
        },
        "packages": {
            name: package_versions[
                name
            ]
            for name in (
                "requests",
                "psutil",
                "bleak",
                "arduino-router-bridge",
            )
        },
        "files": {
            name: {
                "sha256": requirement_hashes[
                    name
                ],
            }
            for name in requirement_files
        },
        "models": {
            "llm": str(
                geniex.get(
                    "model",
                    "",
                )
                or ""
            ).strip(),
            "vision": (
                str(
                    vision.get(
                        "model",
                        "",
                    )
                    or ""
                ).strip()
                if vision.get(
                    "enabled",
                    False,
                )
                else None
            ),
        },
    }


def build_lock_candidate(
    observed,
):
    return {
        "schema_version": (
            LOCK_SCHEMA_VERSION
        ),
        "locked": False,
        "expected": observed,
    }


def load_lock_manifest(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(
            file
        )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Versionslåset måste vara ett JSON-objekt."
        )

    return data


def validate_lock_manifest(
    manifest,
):
    errors = []

    if not isinstance(
        manifest,
        dict,
    ):
        return [
            "Versionslåset måste vara ett objekt."
        ]

    if manifest.get(
        "schema_version"
    ) != LOCK_SCHEMA_VERSION:
        errors.append(
            "Okänd schema_version för versionslåset."
        )

    if manifest.get(
        "locked"
    ) is not True:
        errors.append(
            "Versionslåset är inte markerat locked=true."
        )

    expected = manifest.get(
        "expected"
    )

    if not isinstance(
        expected,
        dict,
    ):
        errors.append(
            "Versionslåset saknar expected-objekt."
        )
        return errors

    for path in _REQUIRED_FIELDS:
        value = _value_at(
            expected,
            path,
        )

        if value is None or (
            isinstance(
                value,
                str,
            )
            and not value.strip()
        ):
            errors.append(
                "Versionslåset saknar "
                + ".".join(
                    path
                )
                + "."
            )

    return errors


def verify_ventuno_stack(
    manifest,
    observed,
):
    errors = validate_lock_manifest(
        manifest
    )

    if errors:
        return {
            "passed": False,
            "errors": errors,
            "mismatches": [],
        }

    mismatches = []
    expected = manifest[
        "expected"
    ]

    for keys, expected_value in _flatten(
        expected
    ):
        observed_value = _value_at(
            observed,
            keys,
        )

        if observed_value != expected_value:
            mismatches.append(
                {
                    "path": ".".join(
                        keys
                    ),
                    "expected": (
                        expected_value
                    ),
                    "observed": (
                        observed_value
                    ),
                }
            )

    return {
        "passed": not mismatches,
        "errors": [],
        "mismatches": mismatches,
    }


def write_json_atomic(
    path,
    data,
):
    path = Path(
        path
    )
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = path.with_suffix(
        path.suffix
        + ".tmp"
    )
    temporary.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(
        path
    )
    return path
