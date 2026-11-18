"""Opt-in TWO-PROCESS App Lab↔MyAI AF_UNIX rehearsal; fake AI only.

No VENTUNO deployment, App Lab import, microphone, speaker, real MyAICore,
GenieX, network, daemon or production configuration. A parent creates an
owner-private temporary socket and transfers a fresh one-turn HMAC secret
through two different inherited anonymous pipe FDs, never argv or env.
The separate client/server child processes exercise the existing signed
protocol, then exit. Both processes use the SAME non-root UID: this is
NOT yet a test of separate production UIDs, mount namespaces or real ASR.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import time

from core.app_lab_unix_final_text import OneSessionReplayGuard
from core.app_lab_voice_handoff import AppLabFinalTextHandoff
from core.app_lab_private_reply_server import serve_one_authenticated_connected_turn
from core.app_lab_private_socket_rehearsal import (
    _SYNTHETIC_ANSWER, _SYNTHETIC_TRANSCRIPT, _SyntheticMyAI,
)
from integrations.arduino_app_lab.alma_reference.private_reply import (
    OneSessionReplyGuard,
)
from integrations.arduino_app_lab.alma_reference.private_socket_client import (
    exchange_final_over_connected_socket,
)

_BOOTSTRAP_SIZE = 72
_TIMEOUT_SECONDS = 8
_TEST_MODES = frozenset(("ready", "blocked", "uncertain", "bad-client-key"))


def _read_bootstrap(fd):
    if type(fd) is not int or fd < 3:
        raise ValueError("Missing dedicated private bootstrap pipe")
    info = os.fstat(fd)
    if not stat.S_ISFIFO(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("Bootstrap descriptor is not a private pipe")
    with os.fdopen(fd, "rb", closefd=True) as pipe:
        data = pipe.read(_BOOTSTRAP_SIZE + 1)
    if len(data) != _BOOTSTRAP_SIZE:
        raise ValueError("Invalid one-turn bootstrap")
    secret = data[:32]
    session = data[32:48].hex()
    request = data[48:64].hex()
    issued_at = int.from_bytes(data[64:72], byteorder="big")
    return secret, session, request, issued_at


def _child(role, bootstrap_fd, locator, mode):
    """Only process-local synthetic behavior, never a production endpoint."""
    if role not in ("server", "client") or mode not in _TEST_MODES:
        return {"status": "invalid-test-role"}
    if os.name != "posix" or os.getuid() <= 0:
        return {"status": "non-root-linux-required"}
    secret, session, request, issued_at = _read_bootstrap(bootstrap_fd)
    uid = os.getuid()
    if role == "server":
        listener_fd = int(locator)
        with socket.socket(fileno=listener_fd) as listener:
            listener.settimeout(3.0)
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(2.0)
                fake = _SyntheticMyAI(
                    "ready" if mode == "bad-client-key" else mode
                )
                result = serve_one_authenticated_connected_turn(
                    connection,
                    expected_peer_uid=uid,
                    secret=secret,
                    active_session=session,
                    request_guard=OneSessionReplayGuard(session_id=session),
                    handoff=AppLabFinalTextHandoff(fake, enabled=True),
                    session_active=lambda: True,
                    asr_released=lambda: True,
                    stop_requested=lambda: False,
                    clock=time.time,
                    enabled=True,
                )
        return {"status": result["status"],
                "reply_status": result.get("reply_status"),
                "fake_dispatches": fake.calls}
    # The only transcript ever sent is a fixed harmless Swedish test.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(2.0)
        conn.connect(locator)
        answer = exchange_final_over_connected_socket(
            conn,
            secret=secret,
            session_id=session,
            request_id=request,
            issued_at=issued_at,
            text=_SYNTHETIC_TRANSCRIPT,
            expected_peer_uid=uid,
            reply_guard=OneSessionReplyGuard(session_id=session),
            session_active=lambda: True,
            asr_released=lambda: True,
            stop_requested=lambda: False,
            clock=time.time,
            max_wait_seconds=3.0,
            enabled=True,
        )
    # Do not print even synthetic speech; expose only readiness and equality.
    return {"status": answer["status"],
            "expected_synthetic_answer": answer == {
                "status": "ready", "answer": _SYNTHETIC_ANSWER,
            }}


def _write_pipe_secret(bootstrap):
    # Short fixed-size (72-byte) write cannot fill a new anonymous pipe.
    read_fd, write_fd = os.pipe()
    try:
        written = os.write(write_fd, bootstrap)
        if written != _BOOTSTRAP_SIZE:
            raise OSError("Incomplete one-turn bootstrap")
    except BaseException:
        os.close(read_fd)
        raise
    finally:
        os.close(write_fd)
    return read_fd


def _run_subprocess(role, key_fd, endpoint_locator, mode, *, repo_root, extra_fds=()):
    # Process arguments and environment carry NO secret, transcript or answer.
    args = (
        sys.executable, "-m",
        "core.app_lab_private_process_rehearsal",
        "--synthetic-child", role, str(key_fd),
        str(endpoint_locator), mode,
    )
    return subprocess.Popen(
        args,
        cwd=str(repo_root),
        env={"PYTHONPATH": str(repo_root), "PYTHONNOUSERSITE": "1",
             "LANG": "C.UTF-8"},
        pass_fds=(key_fd, *extra_fds),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        start_new_session=True,
    )


def _receive_process_report(process):
    try:
        out, _err = process.communicate(timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        return {"status": "child-timeout"}
    if process.returncode != 0 or len(out) > 512:
        return {"status": "child-rejected"}
    try:
        report = json.loads(out.decode("utf-8", "strict"))
    except (UnicodeError, ValueError, TypeError):
        return {"status": "child-rejected"}
    return report if type(report) is dict else {"status": "child-rejected"}


def rehearse_two_private_processes(*, enabled=False, mode="ready"):
    """One real private socket, two independent processes, fake AI only.

    No manual command, filepath, credential, client speech, provider class or
    service configuration may be supplied by the caller. No background task.
    """
    if enabled is not True:
        return {"status": "disabled"}
    if type(mode) is not str or mode not in _TEST_MODES:
        return {"status": "invalid-test-mode"}
    if os.name != "posix" or not hasattr(socket, "SO_PEERCRED"):
        return {"status": "linux-required"}
    uid = os.getuid()
    if uid <= 0:
        return {"status": "non-root-test-user-required"}

    secret = secrets.token_bytes(32)
    session_bytes = secrets.token_bytes(16)
    request_bytes = secrets.token_bytes(16)
    issued_at = int(time.time())
    bootstrap = (secret + session_bytes + request_bytes
                 + issued_at.to_bytes(8, "big"))
    # A deliberately wrong client key tests that HMAC verification rejects
    # before any synthetic MyAI dispatch.
    altered = bytes([secret[0] ^ 1]) + secret[1:]
    client_bootstrap = (
        altered + bootstrap[32:] if mode == "bad-client-key" else bootstrap
    )
    server = None
    client = None
    with tempfile.TemporaryDirectory(prefix="myai-two-process-") as temporary:
        root = Path(temporary)
        endpoint = root / "one-turn.sock"
        info = root.lstat()
        if (not stat.S_ISDIR(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o700
                or info.st_uid != uid):
            return {"status": "private-directory-rejected"}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.settimeout(3.0)
            listener.bind(str(endpoint))
            os.chmod(endpoint, 0o600)
            info = endpoint.lstat()
            if (not stat.S_ISSOCK(info.st_mode)
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != uid):
                return {"status": "private-socket-rejected"}
            listener.listen(1)
            # Also clean the first child when the second launch fails.
            # If either private bootstrap pipe fails, close the other FD.
            server_key_fd = None
            client_key_fd = None
            try:
                server_key_fd = _write_pipe_secret(bootstrap)
                client_key_fd = _write_pipe_secret(client_bootstrap)
                repo_root = Path(__file__).resolve().parents[1]
                server = _run_subprocess(
                    "server", server_key_fd, listener.fileno(), mode,
                    repo_root=repo_root, extra_fds=(listener.fileno(),),
                )
                client = _run_subprocess(
                    "client", client_key_fd, endpoint, mode,
                    repo_root=repo_root,
                )
            except (OSError, ValueError):
                for proc in (client, server):
                    if proc is not None and proc.poll() is None:
                        proc.kill()
                        proc.communicate()
                return {"status": "process-start-rejected"}
            finally:
                for descriptor in (server_key_fd, client_key_fd):
                    if descriptor is not None:
                        os.close(descriptor)

            try:
                client_report = _receive_process_report(client)
                server_report = _receive_process_report(server)
            finally:
                for proc in (client, server):
                    if proc is not None and proc.poll() is None:
                        proc.kill()
                        proc.communicate()
    if mode == "bad-client-key":
        if (client_report.get("status") == "private-exchange-rejected"
                and server_report == {
                    "status": "authentication-or-frame-rejected",
                    "reply_status": None, "fake_dispatches": 0,
                }):
            return {"status": "authentication-test-passed",
                    "private_endpoint_removed": not endpoint.exists()}
        return {"status": "rehearsal-rejected"}
    target = "ready" if mode == "ready" else "withheld"
    if (client_report.get("status") == target
            and server_report.get("status") == "sent"
            and server_report.get("reply_status") == target
            and server_report.get("fake_dispatches") == 1
            and (mode != "ready"
                 or client_report.get("expected_synthetic_answer") is True)):
        return {"status": "test-passed" if mode == "ready" else "test-withheld",
                "processes": 2,
                "private_endpoint_removed": not endpoint.exists()}
    return {"status": "rehearsal-rejected"}


def _main(argv):
    if len(argv) == 5 and argv[0] == "--synthetic-child":
        _flag, role, fd, locator, mode = argv
        try:
            result = _child(role, int(fd), locator, mode)
        except (ValueError, OSError, PermissionError, TimeoutError):
            result = {"status": "child-rejected"}
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return 0
    # Human invocation is never a service, and does not perform any I/O.
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
