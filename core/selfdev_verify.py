import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from core.selfdev_workspace import (
    SelfDevWorkspace,
)


class SelfDevVerifier:
    def __init__(
        self,
        workspace,
        *,
        bwrap_path=None,
        python_executable=None,
        command_runner=None,
        timeout_seconds=300,
        max_output_chars=20_000,
    ):
        if not isinstance(
            workspace,
            SelfDevWorkspace,
        ):
            raise TypeError(
                "workspace måste vara en SelfDevWorkspace."
            )

        self.workspace = workspace
        self.bwrap_path = (
            bwrap_path
            if bwrap_path is not None
            else shutil.which(
                "bwrap"
            )
        )
        self.python_executable = str(
            python_executable
            or sys.executable
        )
        self.command_runner = (
            command_runner
            or self._default_runner
        )
        self.timeout_seconds = max(
            1.0,
            float(
                timeout_seconds
            ),
        )
        self.max_output_chars = max(
            1000,
            int(
                max_output_chars
            ),
        )

    @staticmethod
    def _default_runner(
        command,
        *,
        timeout,
    ):
        # Sanitize even the host-side Bubblewrap launcher environment:
        # untrusted host variables (notably PYTHONPATH/LD_PRELOAD and
        # API credentials) must not reach the verifier subprocess.
        runner_environment = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": "/tmp",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=runner_environment,
        )

    def _system_ro_paths(self):
        candidates = [
            "/usr",
            "/bin",
            "/lib",
            "/lib64",
            "/etc",
        ]

        return [
            path
            for path in candidates
            if Path(
                path
            ).exists()
        ]

    def _sandbox_command(
        self,
        payload,
    ):
        if not self.bwrap_path:
            raise RuntimeError(
                "Selfdev-verifiering kräver Bubblewrap (bwrap). "
                "Ingen osandboxad fallback till host-körning tillåts."
            )

        command = [
            str(
                self.bwrap_path
            ),
            "--die-with-parent",
            "--new-session",
            "--unshare-all",
            # Drop all inherited environment variables before running any
            # staged code; keep only the explicit safe settings below.
            "--clearenv",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
        ]

        for path in self._system_ro_paths():
            command.extend(
                [
                    "--ro-bind",
                    path,
                    path,
                ]
            )

        command.extend(
            [
                # The sandbox must never mutate the staged files that it
                # is supposed to validate. Post-run rehashes alone cannot
                # detect a transient edit that was restored before exit.
                "--ro-bind",
                str(
                    self.workspace.workspace_root
                ),
                "/workspace",
                "--chdir",
                "/workspace",
                "--setenv",
                "HOME",
                "/tmp",
                # bwrap --clearenv preserves PWD; replace its inherited
                # pathname after --chdir with the sandbox-only location.
                "--setenv",
                "PWD",
                "/workspace",
                "--setenv",
                "PATH",
                "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "--setenv",
                "LANG",
                "C.UTF-8",
                "--setenv",
                "LC_ALL",
                "C.UTF-8",
                "--setenv",
                "PYTHONDONTWRITEBYTECODE",
                "1",
                # Explicit py_compile still writes .pyc even with
                # PYTHONDONTWRITEBYTECODE; redirect that cache to the
                # sandbox's private writable tmpfs, never the workspace.
                "--setenv",
                "PYTHONPYCACHEPREFIX",
                "/tmp/myai-pycache",
                "--setenv",
                "XDG_CACHE_HOME",
                "/tmp/myai-cache",
                "--setenv",
                "PYTEST_ADDOPTS",
                "-p no:cacheprovider",
            ]
        )
        command.extend(
            payload
        )
        return command

    def build_command(self):
        return self._sandbox_command(
            [
                self.python_executable,
                "-m",
                "pytest",
                "-q",
            ]
        )

    def build_validation_commands(
        self,
        changes=None,
    ):
        changes = (
            changes
            if changes is not None
            else self.workspace.changed_files()
        )
        paths = sorted(
            set(
                changes["changed"]
                + changes["added"]
            )
        )
        commands = []

        for relative in paths:
            suffix = Path(
                relative
            ).suffix.lower()
            workspace_path = (
                "/workspace/"
                + relative
            )

            if suffix == ".py":
                commands.append(
                    (
                        "python-compile",
                        relative,
                        self._sandbox_command(
                            [
                                self.python_executable,
                                "-m",
                                "py_compile",
                                workspace_path,
                            ]
                        ),
                    )
                )
            elif suffix == ".json":
                commands.append(
                    (
                        "json",
                        relative,
                        self._sandbox_command(
                            [
                                self.python_executable,
                                "-m",
                                "json.tool",
                                workspace_path,
                            ]
                        ),
                    )
                )
            elif suffix == ".toml":
                commands.append(
                    (
                        "toml",
                        relative,
                        self._sandbox_command(
                            [
                                self.python_executable,
                                "-c",
                                (
                                    "import pathlib,tomllib,sys;"
                                    "tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))"
                                ),
                                workspace_path,
                            ]
                        ),
                    )
                )
            elif suffix == ".sh":
                bash = shutil.which(
                    "bash"
                )
                if not bash:
                    raise RuntimeError(
                        "Selfdev-verifiering av shell-filer kräver bash."
                    )
                commands.append(
                    (
                        "shell",
                        relative,
                        self._sandbox_command(
                            [
                                bash,
                                "-n",
                                workspace_path,
                            ]
                        ),
                    )
                )

        return commands

    def verify(self):
        changes = (
            self.workspace
            .changed_files()
        )

        if changes[
            "deleted"
        ]:
            raise RuntimeError(
                "Selfdev-promotion stöder inte filradering i denna fas."
            )

        validation_commands = (
            self.build_validation_commands(
                changes
            )
        )
        commands = (
            validation_commands
            + [
                (
                    "pytest",
                    None,
                    self.build_command(),
                )
            ]
        )
        started = time.monotonic()
        checks = []
        stdout_parts = []
        stderr_parts = []
        error = None
        returncode = 0

        for check_type, path, command in commands:
            try:
                result = self.command_runner(
                    command,
                    timeout=self.timeout_seconds,
                )
                # subprocess.CompletedProcess supplies a real integer.
                # Coercing strings, booleans or floats via int() could turn
                # a synthetic/malformed runner result into false success.
                check_returncode = getattr(result, "returncode", None)
                if type(check_returncode) is not int:
                    raise TypeError(
                        "Sandboxkörningen saknar giltig heltalsreturkod."
                    )
                check_stdout = str(
                    getattr(
                        result,
                        "stdout",
                        "",
                    )
                    or ""
                )
                check_stderr = str(
                    getattr(
                        result,
                        "stderr",
                        "",
                    )
                    or ""
                )
                check_error = None
            except Exception as exc:
                check_returncode = -1
                check_stdout = ""
                check_stderr = ""
                check_error = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

            checks.append(
                {
                    "type": check_type,
                    "path": path,
                    "returncode": (
                        check_returncode
                    ),
                    "passed": (
                        check_returncode == 0
                        and check_error is None
                    ),
                    "error": check_error,
                }
            )

            if check_stdout:
                stdout_parts.append(
                    check_stdout
                )
            if check_stderr:
                stderr_parts.append(
                    check_stderr
                )

            if (
                check_returncode != 0
                or check_error is not None
            ):
                returncode = (
                    check_returncode
                )
                error = check_error
                break

        stdout = "\n".join(
            stdout_parts
        )
        stderr = "\n".join(
            stderr_parts
        )
        elapsed = (
            time.monotonic()
            - started
        )
        # Rehash after commands: sandbox validation may have altered staged
        # code, and the active source may have changed while checks ran.
        # Never persist a passing record for a workspace/version we did not
        # actually validate. Promotion independently rechecks this later.
        after_checks = self.workspace.changed_files()
        source_drift = self.workspace.source_drift()
        unchanged = (
            after_checks["manifest_digest"] == changes["manifest_digest"]
            and after_checks["changed"] == changes["changed"]
            and after_checks["added"] == changes["added"]
            and after_checks["deleted"] == changes["deleted"]
        )
        if not unchanged and error is None:
            error = "Staging-workspacen ändrades under verifieringen."
        if source_drift and error is None:
            error = "Aktiv källkod ändrades under verifieringen."
        if error is not None and returncode == 0:
            # A verifier-level integrity failure is not subprocess success.
            returncode = -1
        passed = (
            returncode == 0
            and error is None
            and unchanged
            and not source_drift
            and all(check["passed"] for check in checks)
        )
        record = {
            "session_id": (
                self.workspace
                .session_id
            ),
            "passed": passed,
            "returncode": (
                returncode
            ),
            "elapsed_seconds": round(
                elapsed,
                3,
            ),
            "workspace_manifest_digest": (
                changes[
                    "manifest_digest"
                ]
            ),
            "changed": (
                changes[
                    "changed"
                ]
            ),
            "added": (
                changes[
                    "added"
                ]
            ),
            "deleted": (
                changes[
                    "deleted"
                ]
            ),
            "source_drift": source_drift,
            "sandbox": "bubblewrap",
            "network_isolated": True,
            "host_devices_exposed": False,
            "checks": checks,
            "stdout": stdout[
                -self.max_output_chars:
            ],
            "stderr": stderr[
                -self.max_output_chars:
            ],
            "error": error,
            "verified_unix_time": (
                time.time()
            ),
        }
        self.workspace.save_verification(record)

        return record
