from types import SimpleNamespace

from core.deployment_lock import (
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
            "arduino-router-bridge": "0.5.0",
        },
        "files": {
            "requirements-ventuno.txt": {
                "sha256": "abc123",
            },
        },
        "models": {
            "llm": "ai-hub-models/Qwen3-4B-Instruct-2507",
            "vision": None,
        },
    }


def test_collect_stack_uses_observed_versions_only(tmp_path):
    (tmp_path / "requirements-ventuno.txt").write_text(
        "arduino-router-bridge==0.5.0\n",
        encoding="utf-8",
    )

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
        distribution_version=lambda name: "0.5.0",
    )

    assert result["platform"]["system"] == "Linux"
    assert result["platform"]["machine"] == "aarch64"
    assert result["platform"]["python"] == "3.12.7"
    assert result["geniex"]["version"] == "geniex 0.8.0"
    assert (
        result["packages"]["arduino-router-bridge"]
        == "0.5.0"
    )
    assert len(
        result["files"][
            "requirements-ventuno.txt"
        ]["sha256"]
    ) == 64
    assert (
        result["models"]["llm"]
        == "ai-hub-models/Qwen3-4B-Instruct-2507"
    )


def test_capture_candidate_is_not_implicitly_locked():
    candidate = build_lock_candidate(
        observed_stack()
    )

    assert candidate["schema_version"] == 1
    assert candidate["locked"] is False
    assert candidate["expected"] == observed_stack()


def test_matching_locked_manifest_passes():
    manifest = {
        "schema_version": 1,
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
        "schema_version": 1,
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
