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
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
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

    def build_command(self):
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
                "--bind",
                str(
                    self.workspace.workspace_root
                ),
                "/workspace",
                "--chdir",
                "/workspace",
                "--setenv",
                "HOME",
                "/tmp",
                "--setenv",
                "PYTHONDONTWRITEBYTECODE",
                "1",
                self.python_executable,
                "-m",
                "pytest",
                "-q",
            ]
        )

        return command

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

        command = self.build_command()
        started = time.monotonic()

        try:
            result = self.command_runner(
                command,
                timeout=self.timeout_seconds,
            )
            returncode = int(
                getattr(
                    result,
                    "returncode",
                    1,
                )
            )
            stdout = str(
                getattr(
                    result,
                    "stdout",
                    "",
                )
                or ""
            )
            stderr = str(
                getattr(
                    result,
                    "stderr",
                    "",
                )
                or ""
            )
            error = None
        except Exception as exc:
            returncode = -1
            stdout = ""
            stderr = ""
            error = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        elapsed = (
            time.monotonic()
            - started
        )
        passed = (
            returncode == 0
            and error is None
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
            "source_drift": (
                self.workspace
                .source_drift()
            ),
            "sandbox": "bubblewrap",
            "network_isolated": True,
            "host_devices_exposed": False,
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
        self.workspace.verification_path.write_text(
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        return record
