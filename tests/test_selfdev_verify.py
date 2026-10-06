from types import SimpleNamespace

import pytest

from core.selfdev_verify import (
    SelfDevVerifier,
)
from core.selfdev_workspace import (
    SelfDevWorkspace,
)


def make_workspace(tmp_path):
    project = (
        tmp_path
        / "project"
    )
    (project / "core").mkdir(
        parents=True
    )
    (project / "tests").mkdir()
    (
        project
        / "core"
        / "example.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (
        project
        / "tests"
        / "test_example.py"
    ).write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )

    workspace = (
        SelfDevWorkspace.create(
            project,
            "verify1",
        )
    )
    workspace.write_text(
        "core/example.py",
        "VALUE = 2\n",
    )
    return workspace


def test_verifier_refuses_host_execution_without_bubblewrap(
    tmp_path,
):
    workspace = make_workspace(
        tmp_path
    )
    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="",
    )

    with pytest.raises(
        RuntimeError,
        match="Bubblewrap",
    ):
        verifier.build_command()


def test_verifier_command_is_network_and_device_isolated(
    tmp_path,
):
    workspace = make_workspace(
        tmp_path
    )
    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/bin/python3",
    )

    command = verifier.build_command()

    assert "--unshare-all" in command
    assert "--dev" in command
    dev_index = command.index(
        "--dev"
    )
    assert command[
        dev_index + 1
    ] == "/dev"
    assert "--bind" in command
    assert "/workspace" in command
    assert command[-3:] == [
        "-m",
        "pytest",
        "-q",
    ]


def test_successful_verification_records_manifest_and_isolation(
    tmp_path,
):
    workspace = make_workspace(
        tmp_path
    )
    calls = []

    def runner(
        command,
        *,
        timeout,
    ):
        calls.append(
            (
                command,
                timeout,
            )
        )
        return SimpleNamespace(
            returncode=0,
            stdout="10 passed",
            stderr="",
        )

    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/bin/python3",
        command_runner=runner,
        timeout_seconds=12,
    )

    result = verifier.verify()

    assert result["passed"] is True
    assert result["sandbox"] == "bubblewrap"
    assert result["network_isolated"] is True
    assert result["host_devices_exposed"] is False
    assert result["changed"] == [
        "core/example.py"
    ]
    assert result[
        "workspace_manifest_digest"
    ]
    assert calls[0][1] == 12
    assert (
        workspace
        .verification_path
        .exists()
    )


def test_failed_verification_is_recorded_not_promoted(
    tmp_path,
):
    workspace = make_workspace(
        tmp_path
    )

    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="/usr/bin/bwrap",
        command_runner=lambda command, timeout: (
            SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="failed",
            )
        ),
    )

    result = verifier.verify()

    assert result["passed"] is False
    assert result["returncode"] == 1
    assert result["stderr"] == "failed"


def test_verifier_rejects_deleted_files(
    tmp_path,
):
    workspace = make_workspace(
        tmp_path
    )
    (
        workspace.workspace_root
        / "core"
        / "example.py"
    ).unlink()

    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="/usr/bin/bwrap",
    )

    with pytest.raises(
        RuntimeError,
        match="filradering",
    ):
        verifier.verify()


def test_type_aware_validation_commands_cover_supported_formats(
    tmp_path,
    monkeypatch,
):
    workspace = make_workspace(
        tmp_path
    )
    workspace.write_text(
        "config/example.json",
        '{"ok": true}\n',
    )
    workspace.write_text(
        "config/example.toml",
        'name = "myai"\n',
    )
    workspace.write_text(
        "scripts/example.sh",
        "#!/bin/sh\necho ok\n",
    )
    workspace.write_text(
        "docs/example.md",
        "# Documentation\n",
    )
    monkeypatch.setattr(
        "core.selfdev_verify.shutil.which",
        lambda name: (
            "/bin/bash"
            if name == "bash"
            else None
        ),
    )
    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/bin/python3",
    )

    commands = (
        verifier
        .build_validation_commands()
    )
    checks = {
        (kind, path): command
        for kind, path, command
        in commands
    }

    assert (
        "python-compile",
        "core/example.py",
    ) in checks
    assert (
        "json",
        "config/example.json",
    ) in checks
    assert (
        "toml",
        "config/example.toml",
    ) in checks
    assert (
        "shell",
        "scripts/example.sh",
    ) in checks
    assert not any(
        path == "docs/example.md"
        for _, path in checks
    )
    assert checks[
        (
            "shell",
            "scripts/example.sh",
        )
    ][-2:] == [
        "-n",
        "/workspace/scripts/example.sh",
    ]


def test_verifier_stops_before_pytest_when_type_check_fails(
    tmp_path,
):
    workspace = make_workspace(
        tmp_path
    )
    workspace.write_text(
        "config/broken.json",
        "{broken",
    )
    calls = []

    def runner(
        command,
        *,
        timeout,
    ):
        calls.append(
            command
        )
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="syntax error",
        )

    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/bin/python3",
        command_runner=runner,
    )

    result = verifier.verify()

    assert result["passed"] is False
    assert len(calls) == 1
    assert result["checks"][0][
        "type"
    ] == "json"
    assert result["checks"][0][
        "path"
    ] == "config/broken.json"
    assert result["checks"][0][
        "passed"
    ] is False
