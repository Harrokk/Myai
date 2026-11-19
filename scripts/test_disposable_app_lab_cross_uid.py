"""Networkless, disposable Docker-only real cross-UID App Lab/MyAI IPC test.

No VENTUNO files or users, real AI, audio, production credentials or services.
Three different synthetic Linux UIDs and a dedicated IPC GID are used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import select
import signal
import socket
import stat
import tempfile
import time

from core.app_lab_private_reply_server import serve_one_authenticated_connected_turn
from core.app_lab_unix_final_text import OneSessionReplayGuard
from core.app_lab_voice_handoff import AppLabFinalTextHandoff
from core.app_lab_private_socket_rehearsal import (
    _SyntheticMyAI, _SYNTHETIC_TRANSCRIPT, _SYNTHETIC_ANSWER,
)
from integrations.arduino_app_lab.alma_reference.private_reply import OneSessionReplyGuard
from integrations.arduino_app_lab.alma_reference.private_socket_client import (
    exchange_final_over_connected_socket,
)

SERVER_UID = 23211
CLIENT_UID = 23212
OUTSIDER_UID = 23213
IPC_GID = 23220
BOOT_BYTES = 72


def require_disposable():
    if (os.name != "posix" or os.geteuid() != 0
            or not hasattr(socket, "SO_PEERCRED")
            or not Path("/.dockerenv").exists()
            or os.environ.get("MYAI_DISPOSABLE_ALMA_UID_TEST") != "yes"
            or os.environ.get("MYAI_RUNNER_ENVIRONMENT") != "github-hosted"
            or not Path("/tmp").is_dir()):
        raise RuntimeError("Only disposable hosted networkless Docker fixture allowed")


def drop(uid, gid):
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    assert os.geteuid() == uid and os.getegid() == gid and not os.getgroups()


def denied(path):
    try:
        path.read_bytes()
    except PermissionError:
        return True
    return False


def bootstrap_pipe(raw):
    assert len(raw) == BOOT_BYTES
    reader, writer = os.pipe()
    try:
        assert os.write(writer, raw) == BOOT_BYTES
    finally:
        os.close(writer)
    return reader


def get_bootstrap(fd):
    info = os.fstat(fd)
    if not stat.S_ISFIFO(info.st_mode) or info.st_uid != 0:
        raise PermissionError("Unexpected synthetic bootstrap descriptor")
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(BOOT_BYTES + 1)
    if len(raw) != BOOT_BYTES:
        raise ValueError("Incomplete bootstrap")
    return raw[:32], raw[32:48].hex(), raw[48:64].hex(), int.from_bytes(raw[64:], "big")


def child_server(root, boot_fd, ready_fd, mode):
    drop(SERVER_UID, IPC_GID)
    secret, session, _request, _issued = get_bootstrap(boot_fd)
    assert denied(root / "client" / "marker")
    endpoint = root / "ipc" / "voice.sock"
    previous = os.umask(0o117)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.settimeout(4.0)
            listener.bind(str(endpoint))
            os.chmod(endpoint, 0o660)
            info = endpoint.lstat()
            assert (stat.S_ISSOCK(info.st_mode) and info.st_uid == SERVER_UID
                    and info.st_gid == IPC_GID
                    and stat.S_IMODE(info.st_mode) == 0o660)
            listener.listen(1)
            os.write(ready_fd, b"1")
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(2.0)
                fake = _SyntheticMyAI("ready" if mode == "wrong-key" else mode)
                outcome = serve_one_authenticated_connected_turn(
                    conn, expected_peer_uid=CLIENT_UID, secret=secret,
                    active_session=session,
                    request_guard=OneSessionReplayGuard(session_id=session),
                    handoff=AppLabFinalTextHandoff(fake, enabled=True),
                    session_active=lambda: True,
                    asr_released=lambda: True,
                    stop_requested=lambda: False,
                    enabled=True, clock=time.time,
                )
        return {"status": outcome.get("status"),
                "reply": outcome.get("reply_status"),
                "calls": fake.calls}
    finally:
        os.umask(previous)


def child_client(root, boot_fd):
    drop(CLIENT_UID, IPC_GID)
    secret, session, request, issued = get_bootstrap(boot_fd)
    assert denied(root / "server" / "marker")
    assert (root / "client" / "marker").read_bytes() == b"fake-client"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(1.5)
        connection.connect(str(root / "ipc" / "voice.sock"))
        answer = exchange_final_over_connected_socket(
            connection, secret=secret, session_id=session,
            request_id=request, issued_at=issued,
            text=_SYNTHETIC_TRANSCRIPT,
            expected_peer_uid=SERVER_UID,
            reply_guard=OneSessionReplyGuard(session_id=session),
            session_active=lambda: True, asr_released=lambda: True,
            stop_requested=lambda: False, enabled=True,
            clock=time.time, max_wait_seconds=3.0,
        )
    return {"status": answer.get("status"),
            "matches_fixed_answer": answer == {
                "status": "ready", "answer": _SYNTHETIC_ANSWER}}


def child_outsider(root):
    drop(OUTSIDER_UID, OUTSIDER_UID)
    assert denied(root / "server" / "marker")
    assert denied(root / "client" / "marker")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(root / "ipc" / "voice.sock"))
    except PermissionError:
        return {"status": "denied"}
    return {"status": "unexpected-access"}


def spawn(role, root, boot_fd=None, mode="ready"):
    result_r, result_w = os.pipe()
    ready_r, ready_w = os.pipe() if role == "server" else (None, None)
    pid = os.fork()
    if pid == 0:
        os.close(result_r)
        if ready_r is not None:
            os.close(ready_r)
        try:
            if role == "server":
                result = child_server(root, boot_fd, ready_w, mode)
            elif role == "client":
                result = child_client(root, boot_fd)
            else:
                result = child_outsider(root)
        except BaseException as error:
            result = {"status": "child-error",
                      "error": type(error).__name__}
        payload = json.dumps(result, sort_keys=True).encode("ascii")
        try:
            if len(payload) <= 512:
                os.write(result_w, payload)
        finally:
            os._exit(0)
    os.close(result_w)
    if boot_fd is not None:
        os.close(boot_fd)
    if ready_w is not None:
        os.close(ready_w)
    return pid, result_r, ready_r


def read_small(fd, timeout=5.0):
    readables, _, _ = select.select([fd], [], [], timeout)
    if not readables:
        raise TimeoutError("Disposable fixture child report timed out")
    data = os.read(fd, 1024)
    if not 0 < len(data) <= 512:
        raise ValueError("Invalid child report")
    return json.loads(data.decode("ascii"))


def reap(pid):
    try:
        finished, _ = os.waitpid(pid, os.WNOHANG)
        if not finished:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
    except (ChildProcessError, ProcessLookupError):
        pass


def make_dirs(root):
    (root / "ipc").mkdir()
    for key, data in (("server", b"fake-server"), ("client", b"fake-client")):
        directory = root / key
        directory.mkdir()
        (directory / "marker").write_bytes(data)
    for key, uid, gid in (("server", SERVER_UID, SERVER_UID),
                          ("client", CLIENT_UID, CLIENT_UID)):
        marker = root / key / "marker"
        os.chown(marker, uid, gid)
        marker.chmod(0o600)
        directory = root / key
        os.chown(directory, uid, gid)
        directory.chmod(0o700)
    os.chown(root / "ipc", SERVER_UID, IPC_GID)
    (root / "ipc").chmod(0o750)
    root.chmod(0o755)


def reset_permissions(root):
    # Contained Docker root has only CHOWN/FOWNER, never DAC_OVERRIDE.
    for key in ("ipc", "server", "client"):
        directory = root / key
        os.chown(directory, 0, 0)
        directory.chmod(0o700)
        for child in directory.iterdir():
            os.chown(child, 0, 0)
            child.chmod(0o600)


def run_case(mode):
    if mode not in {"ready", "blocked", "wrong-key"}:
        raise ValueError("Unrecognized synthetic case")
    secret = secrets.token_bytes(32)
    payload = (secret + secrets.token_bytes(16) + secrets.token_bytes(16)
               + int(time.time()).to_bytes(8, "big"))
    altered = bytes([secret[0] ^ 1]) + payload[1:]
    children, pipes = [], []
    with tempfile.TemporaryDirectory(prefix="myai-crossuid-", dir="/tmp") as name:
        root = Path(name)
        try:
            make_dirs(root)
            server = spawn("server", root, bootstrap_pipe(payload), mode)
            children.append(server[0])
            pipes.extend((server[1], server[2]))
            ready_fd = server[2]
            readable, _, _ = select.select([ready_fd], [], [], 3.0)
            if not readable or os.read(ready_fd, 1) != b"1":
                raise AssertionError("Server socket was not ready")

            stranger = spawn("outsider", root)
            children.append(stranger[0])
            pipes.append(stranger[1])
            assert read_small(stranger[1]) == {"status": "denied"}

            client_raw = altered if mode == "wrong-key" else payload
            client = spawn("client", root, bootstrap_pipe(client_raw))
            children.append(client[0])
            pipes.append(client[1])
            cr = read_small(client[1])
            sr = read_small(server[1])
        finally:
            for pid in children:
                reap(pid)
            for fd in pipes:
                try:
                    os.close(fd)
                except OSError:
                    pass
            reset_permissions(root)
    if mode == "wrong-key":
        assert cr["status"] == "private-exchange-rejected", cr
        assert sr == {"status": "authentication-or-frame-rejected",
                      "reply": None, "calls": 0}, sr
        return "signature-rejected"
    expect = "ready" if mode == "ready" else "withheld"
    assert cr["status"] == expect, cr
    assert sr == {"status": "sent", "reply": expect, "calls": 1}, sr
    if mode == "ready":
        assert cr["matches_fixed_answer"] is True
    return expect


def main():
    require_disposable()
    outcomes = {mode: run_case(mode) for mode in
                ("ready", "blocked", "wrong-key")}
    assert outcomes == {
        "ready": "ready", "blocked": "withheld",
        "wrong-key": "signature-rejected",
    }
    print(json.dumps({
        "result": "PASS", "real_distinct_linux_uids": 3,
        "cross_uid_signed_response": True,
        "outsider_private_file_and_socket_access_denied": True,
        "keys_only_anonymous_pipe": True,
        "real_myai_or_audio": False,
        "ventuno_deployment_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
