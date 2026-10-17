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
    assert "--clearenv" in command
    assert command.index("--unshare-all") < command.index("--clearenv")
    assert "--dev" in command
    dev_index = command.index(
        "--dev"
    )
    assert command[
        dev_index + 1
    ] == "/dev"
    # Staged code is data under test, never a writable sandbox mount.
    assert "--bind" not in command
    mount_at = command.index("/workspace")
    assert command[mount_at - 2] == "--ro-bind"
    assert command[mount_at - 1] == str(workspace.workspace_root)
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


def test_verifier_marks_staging_mutation_during_checks_as_failure(tmp_path):
    workspace = make_workspace(tmp_path)
    staged = workspace.workspace_root / "core" / "example.py"
    calls = []

    def alter_staging(command, *, timeout):
        calls.append(command)
        if len(calls) == 1:
            # Bypass the workspace API: model a noncooperating sandbox writer.
            staged.write_text("UNVERIFIED = True\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    verifier = SelfDevVerifier(
        workspace, bwrap_path="/usr/bin/bwrap", command_runner=alter_staging
    )
    result = verifier.verify()
    assert len(calls) >= 1
    assert result["passed"] is False
    assert result["returncode"] == -1
    assert "Staging-workspacen ändrades" in result["error"]
    assert workspace.read_verification() == result


def test_verifier_marks_source_drift_during_checks_as_failure(tmp_path):
    workspace = make_workspace(tmp_path)
    active = workspace.project_root / "core" / "example.py"
    calls = []

    def alter_active(command, *, timeout):
        calls.append(command)
        if len(calls) == 1:
            active.write_text("UNTRUSTED = True\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    verifier = SelfDevVerifier(
        workspace, bwrap_path="/usr/bin/bwrap", command_runner=alter_active
    )
    result = verifier.verify()
    assert result["passed"] is False
    assert result["returncode"] == -1
    assert "Aktiv källkod ändrades" in result["error"]
    assert result["source_drift"] == ["core/example.py"]
    assert workspace.read_verification() == result


def test_verifier_marks_existing_source_drift_as_failure(tmp_path):
    workspace = make_workspace(tmp_path)
    (workspace.project_root / "core" / "example.py").write_text(
        "UNTRUSTED = True\n", encoding="utf-8"
    )
    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="/usr/bin/bwrap",
        command_runner=lambda command, timeout: SimpleNamespace(
            returncode=0, stdout="checks pass", stderr=""
        ),
    )
    result = verifier.verify()
    assert result["passed"] is False
    assert result["returncode"] == -1
    assert result["source_drift"] == ["core/example.py"]


@pytest.mark.parametrize("returncode", ["0", 0.1, False, None])
def test_verifier_refuses_noninteger_command_runner_returncode(
    tmp_path, returncode
):
    workspace = make_workspace(tmp_path)
    verifier = SelfDevVerifier(
        workspace,
        bwrap_path="/usr/bin/bwrap",
        command_runner=lambda command, timeout: SimpleNamespace(
            returncode=returncode, stdout="ok", stderr=""
        ),
    )
    result = verifier.verify()
    assert result["passed"] is False
    assert result["returncode"] == -1
    assert result["checks"][0]["passed"] is False
    assert result["checks"][0]["returncode"] == -1
    assert result["checks"][0]["error"].startswith("TypeError:")
    assert workspace.read_verification() == result


def test_verifier_marks_removed_staging_file_during_checks_as_failure(
    tmp_path,
):
    workspace = make_workspace(tmp_path)
    staged = workspace.workspace_root / "core" / "example.py"
    calls = []

    def remove_staging(command, *, timeout):
        calls.append(command)
        if len(calls) == 1:
            staged.unlink()
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    verifier = SelfDevVerifier(
        workspace, bwrap_path="/usr/bin/bwrap", command_runner=remove_staging
    )
    result = verifier.verify()
    assert result["passed"] is False
    assert result["returncode"] == -1
    assert "Staging-workspacen ändrades" in result["error"]


def test_verifier_redirects_compile_and_pytest_caches_outside_staging(tmp_path):
    workspace = make_workspace(tmp_path)
    verifier = SelfDevVerifier(
        workspace, bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/bin/python3",
    )
    command = verifier.build_command()

    def env_value(key):
        for i in range(len(command) - 2):
            if command[i:i + 2] == ["--setenv", key]:
                return command[i + 2]
        raise AssertionError(f"Missing sandbox env: {key}")

    assert env_value("HOME") == "/tmp"
    assert env_value("PYTHONDONTWRITEBYTECODE") == "1"
    assert env_value("PYTHONPYCACHEPREFIX").startswith("/tmp/")
    assert env_value("XDG_CACHE_HOME").startswith("/tmp/")
    assert env_value("PYTEST_ADDOPTS") == "-p no:cacheprovider"
    assert "--tmpfs" in command
    assert command[command.index("--tmpfs") + 1] == "/tmp"


def test_all_validation_commands_have_readonly_staging_mount(tmp_path):
    workspace = make_workspace(tmp_path)
    workspace.write_text("config/example.json", '{"ok": true}\n')
    verifier = SelfDevVerifier(
        workspace, bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/bin/python3",
    )

    # .py uses explicit py_compile; .json uses json.tool. Both must have
    # exactly the same read-only workspace mount as pytest.
    commands = [verifier.build_command()] + [
        command for _, _, command in verifier.build_validation_commands()
    ]
    assert len(commands) >= 3
    for command in commands:
        assert "--bind" not in command
        workspace_mounts = [
            i for i, token in enumerate(command)
            if token == "/workspace" and i >= 2
            and command[i - 2] == "--ro-bind"
        ]
        assert len(workspace_mounts) == 1
        index = workspace_mounts[0]
        assert command[index - 1] == str(workspace.workspace_root)
        assert "--unshare-all" in command


def test_default_verifier_runner_does_not_inherit_host_secrets(
    tmp_path, monkeypatch
):
    from core import selfdev_verify as module

    monkeypatch.setenv("MYAI_SYNTHETIC_SECRET", "CANARY-DO-NOT-LEAK")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "untrusted-import-path"))
    monkeypatch.setenv("LD_PRELOAD", str(tmp_path / "fake-library.so"))
    subprocess_calls = []

    def fake_subprocess_run(command, **kwargs):
        subprocess_calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_subprocess_run)
    result = SelfDevVerifier._default_runner(
        ["/usr/bin/bwrap", "--version"], timeout=3
    )

    assert result.returncode == 0
    assert len(subprocess_calls) == 1
    _, kwargs = subprocess_calls[0]
    assert kwargs["timeout"] == 3
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    isolated_environment = kwargs["env"]
    assert isolated_environment["HOME"] == "/tmp"
    assert isolated_environment["LANG"] == "C.UTF-8"
    assert isolated_environment["PATH"].startswith("/usr/local/sbin:")
    assert "MYAI_SYNTHETIC_SECRET" not in isolated_environment
    assert "PYTHONPATH" not in isolated_environment
    assert "LD_PRELOAD" not in isolated_environment
    assert "CANARY-DO-NOT-LEAK" not in repr(isolated_environment)


def test_sandbox_command_reintroduces_only_explicit_env_after_clearenv(
    tmp_path, monkeypatch
):
    workspace = make_workspace(tmp_path)
    monkeypatch.setenv("MYAI_SYNTHETIC_SECRET", "CANARY-DO-NOT-LEAK")
    monkeypatch.setenv("PYTHONPATH", "/outside")
    verifier = SelfDevVerifier(
        workspace, bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/bin/python3",
    )

    command = verifier.build_command()
    assert command.count("--clearenv") == 1
    clear_at = command.index("--clearenv")
    variables = {}
    for i in range(len(command) - 2):
        if command[i] == "--setenv":
            assert i > clear_at
            variables[command[i + 1]] = command[i + 2]
    assert variables["HOME"] == "/tmp"
    assert variables["PATH"] == (
        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )
    assert variables["LANG"] == "C.UTF-8"
    assert variables["LC_ALL"] == "C.UTF-8"
    assert variables["PYTHONPYCACHEPREFIX"].startswith("/tmp/")
    assert "MYAI_SYNTHETIC_SECRET" not in variables
    assert "PYTHONPATH" not in variables
    assert "LD_PRELOAD" not in variables
    assert "CANARY-DO-NOT-LEAK" not in repr(command)


def test_every_selfdev_validation_command_clears_inherited_environment(tmp_path):
    workspace = make_workspace(tmp_path)
    workspace.write_text("config/example.json", '{"ok":true}\n')
    verifier = SelfDevVerifier(
        workspace, bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/bin/python3",
    )

    commands = [verifier.build_command()] + [
        command for _, _, command in verifier.build_validation_commands()
    ]
    assert len(commands) >= 3
    for command in commands:
        assert command.count("--clearenv") == 1
        assert command.index("--clearenv") < command.index("--setenv")
        assert "--unshare-all" in command
        assert "--bind" not in command
        assert "--ro-bind" in command
