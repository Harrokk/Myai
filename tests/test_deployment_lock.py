from types import SimpleNamespace

from core.deployment_lock import (
    LOCK_SCHEMA_VERSION,
    build_lock_candidate,
    collect_ventuno_stack,
    validate_lock_manifest,
    verify_ventuno_stack,
)


def settings():
    return {
        "geniex": {
            "model": "ai-hub-models/Qwen3-4B-Instruct-2507",
        },
        "vision": {
            "enabled": False,
            "model": "qualcomm/Qwen3-VL-4B-Instruct",
        },
    }


def observed_stack():
    return {
        "platform": {
            "system": "Linux",
            "machine": "aarch64",
            "python": "3.12.7",
        },
        "geniex": {
            "version": "geniex 0.8.0",
        },
        "packages": {
            "requests": "2.32.5",
            "psutil": "7.1.0",
            "bleak": "3.0.2",
            "arduino-router-bridge": "0.5.0",
        },
        "files": {
            "requirements.txt": {
                "sha256": "req-main",
            },
            "requirements-ventuno.txt": {
                "sha256": "req-ventuno",
            },
            "requirements-camera.txt": {
                "sha256": "req-camera",
            },
            "requirements-voice.txt": {
                "sha256": "req-voice",
            },
            "requirements-gps.txt": {
                "sha256": "req-gps",
            },
        },
        "models": {
            "llm": "ai-hub-models/Qwen3-4B-Instruct-2507",
            "vision": None,
        },
    }


def test_collect_stack_uses_observed_versions_and_requirement_hashes(
    tmp_path,
):
    requirement_names = (
        "requirements.txt",
        "requirements-ventuno.txt",
        "requirements-camera.txt",
        "requirements-voice.txt",
        "requirements-gps.txt",
    )

    for name in requirement_names:
        (
            tmp_path
            / name
        ).write_text(
            f"# {name}\n",
            encoding="utf-8",
        )

    versions = {
        "requests": "2.32.5",
        "psutil": "7.1.0",
        "bleak": "3.0.2",
        "arduino-router-bridge": "0.5.0",
    }

    result = collect_ventuno_stack(
        settings(),
        tmp_path,
        system="Linux",
        machine="aarch64",
        python_version="3.12.7",
        which=lambda name: (
            "/usr/bin/geniex"
            if name == "geniex"
            else None
        ),
        command_runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout="geniex 0.8.0\n",
            stderr="",
        ),
        distribution_version=lambda name: versions.get(
            name
        ),
    )

    assert result["platform"] == {
        "system": "Linux",
        "machine": "aarch64",
        "python": "3.12.7",
    }
    assert result["geniex"]["version"] == "geniex 0.8.0"
    assert result["packages"] == versions

    for name in requirement_names:
        digest = result[
            "files"
        ][
            name
        ][
            "sha256"
        ]
        assert isinstance(
            digest,
            str,
        )
        assert len(
            digest
        ) == 64

    assert (
        result["models"]["llm"]
        == "ai-hub-models/Qwen3-4B-Instruct-2507"
    )


def test_capture_candidate_is_not_implicitly_locked():
    candidate = build_lock_candidate(
        observed_stack()
    )

    assert (
        candidate["schema_version"]
        == LOCK_SCHEMA_VERSION
    )
    assert candidate["locked"] is False
    assert candidate["expected"] == observed_stack()


def test_matching_locked_manifest_passes():
    manifest = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "locked": True,
        "expected": observed_stack(),
    }

    result = verify_ventuno_stack(
        manifest,
        observed_stack(),
    )

    assert result["passed"] is True
    assert result["errors"] == []
    assert result["mismatches"] == []


def test_version_mismatch_fails_closed():
    manifest = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "locked": True,
        "expected": observed_stack(),
    }
    observed = observed_stack()
    observed["geniex"][
        "version"
    ] = "geniex 0.9.0"

    result = verify_ventuno_stack(
        manifest,
        observed,
    )

    assert result["passed"] is False
    assert result["mismatches"][0][
        "path"
    ] == "geniex.version"


def test_base_dependency_mismatch_fails_closed():
    manifest = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "locked": True,
        "expected": observed_stack(),
    }
    observed = observed_stack()
    observed[
        "packages"
    ][
        "psutil"
    ] = "8.0.0"

    result = verify_ventuno_stack(
        manifest,
        observed,
    )

    assert result["passed"] is False
    assert any(
        item[
            "path"
        ]
        == "packages.psutil"
        for item in result[
            "mismatches"
        ]
    )


def test_requirement_hash_mismatch_fails_closed():
    manifest = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "locked": True,
        "expected": observed_stack(),
    }
    observed = observed_stack()
    observed[
        "files"
    ][
        "requirements.txt"
    ][
        "sha256"
    ] = "different"

    result = verify_ventuno_stack(
        manifest,
        observed,
    )

    assert result["passed"] is False
    assert any(
        item[
            "path"
        ]
        == "files.requirements.txt.sha256"
        for item in result[
            "mismatches"
        ]
    )


def test_unlocked_or_incomplete_manifest_is_rejected():
    manifest = build_lock_candidate(
        observed_stack()
    )
    manifest["expected"][
        "geniex"
    ]["version"] = None

    errors = validate_lock_manifest(
        manifest
    )

    assert any(
        "locked=true"
        in item
        for item in errors
    )
    assert any(
        "geniex.version"
        in item
        for item in errors
    )


def test_old_lock_schema_is_rejected():
    manifest = {
        "schema_version": 1,
        "locked": True,
        "expected": observed_stack(),
    }

    errors = validate_lock_manifest(
        manifest
    )

    assert any(
        "schema_version"
        in item
        for item in errors
    )
