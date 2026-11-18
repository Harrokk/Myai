"""Disabled-by-default real AF_UNIX transport rehearsal using a SYNTHETIC MyAI.

This is an off-device integration fixture, NOT an App Lab or production
service. It opens one temporary user-private Unix socket in an automatically
created directory, creates ephemeral in-memory HMAC/session keys, and runs
the existing signed App Lab client and server once.

No microphone, speaker, model inference, persistent key storage, App Lab
install, daemon, network listener or real MyAICore object is supported.
This does NOT establish separate production UIDs, container mounts,
physical ASR release, hardware consent or QNN arbitration.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import socket
import stat
import tempfile
import threading
import time

from core.app_lab_private_reply_server import serve_one_authenticated_connected_turn
from core.app_lab_unix_final_text import OneSessionReplayGuard
from core.app_lab_voice_handoff import AppLabFinalTextHandoff
from integrations.arduino_app_lab.alma_reference.private_reply import OneSessionReplyGuard
from integrations.arduino_app_lab.alma_reference.private_socket_client import (
    exchange_final_over_connected_socket,
)

_SYNTHETIC_TRANSCRIPT = "Hur fungerar solceller?"
_SYNTHETIC_ANSWER = "Solceller omvandlar ljus till elektricitet."


class _SyntheticMyAI:
    """Hardcoded read-only fixture. Real MyAI cannot be injected here."""

    settings = {"memory": {
        "auto_assess_enabled": False, "auto_save_enabled": False,
        "review_queue_enabled": False, "lifecycle_enabled": False,
    }}

    def __init__(self, mode):
        self.mode = mode
        self.calls = 0

    def respond_voice(self, text, *, plan_verifier):
        self.calls += 1
        if text != _SYNTHETIC_TRANSCRIPT:
            raise ValueError("Unexpected synthetic test phrase")
        # No effectful plan is authorized, even from our fake assistant.
        if plan_verifier({"steps": [{"tool": "write_file"}]}, {}) is not False:
            raise RuntimeError("Unexpected effectful approval")
        if self.mode == "blocked":
            return {
                "answer": "BLOCKED FAKE SECRET", "tool_execution_status": "blocked",
                "manual_reconciliation_required": False,
                "tool_dispatch_blocked": True,
            }
        if self.mode == "uncertain":
            return {
                "answer": "UNCERTAIN FAKE SECRET",
                "tool_execution_status": "unknown",
                "manual_reconciliation_required": True,
                "tool_dispatch_blocked": False,
            }
        return {
            "answer": _SYNTHETIC_ANSWER,
            "tool_execution_status": "not_applicable",
            "manual_reconciliation_required": False,
            "tool_dispatch_blocked": False,
        }


def _private_socket_status(root, endpoint):
    root_stat = root.lstat()
    endpoint_stat = endpoint.lstat()
    return (
        stat.S_ISDIR(root_stat.st_mode)
        and stat.S_IMODE(root_stat.st_mode) == 0o700
        and root_stat.st_uid == os.getuid()
        and stat.S_ISSOCK(endpoint_stat.st_mode)
        and stat.S_IMODE(endpoint_stat.st_mode) == 0o600
        and endpoint_stat.st_uid == os.getuid()
    )


def rehearse_one_private_turn(*, enabled=False, mode="ready",
                             stop_requested=None):
    """Exercise a REAL local socket but only the fixed fake MyAI transcript.

    Returns status and synthetic answer for test assertions only. No logging
    or disk transcript storage. No hardware or actual AI services touched.
    """
    if enabled is not True:
        return {"status": "disabled"}
    if type(mode) is not str or mode not in {"ready", "blocked", "uncertain"}:
        return {"status": "invalid-rehearsal-mode"}
    if stop_requested is not None and not callable(stop_requested):
        return {"status": "invalid-stop-probe"}
    if os.name != "posix" or not hasattr(socket, "SO_PEERCRED"):
        return {"status": "linux-required"}
    uid = os.getuid()
    if uid <= 0:
        return {"status": "non-root-test-user-required"}
    def stopped():
        try:
            return (stop_requested() is not False) if stop_requested else False
        except BaseException:
            return True

    # Neither secret nor identities ever enter a file, log or subprocess.
    secret = secrets.token_bytes(32)
    session = secrets.token_hex(16)
    request = secrets.token_hex(16)
    issued_at = int(time.time())
    fake = _SyntheticMyAI(mode)
    handoff = AppLabFinalTextHandoff(fake, enabled=True)
    server_reports = []
    server_errors = []

    with tempfile.TemporaryDirectory(prefix="myai-private-rehearsal-") as temp:
        root = Path(temp)
        endpoint = root / "turn.sock"
        # Even before chmod, a root dir with mode 0700 protects the path.
        if (root.is_symlink() or not stat.S_ISDIR(root.lstat().st_mode)
                or stat.S_IMODE(root.lstat().st_mode) != 0o700
                or root.stat().st_uid != uid):
            return {"status": "private-path-rejected"}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.settimeout(2.0)
            listener.bind(str(endpoint))
            os.chmod(endpoint, 0o600)
            if not _private_socket_status(root, endpoint):
                return {"status": "private-path-rejected"}
            listener.listen(1)
            def server_worker():
                try:
                    conn, _ = listener.accept()
                    with conn:
                        conn.settimeout(2.0)
                        server_reports.append(serve_one_authenticated_connected_turn(
                            conn, expected_peer_uid=uid, secret=secret,
                            active_session=session,
                            request_guard=OneSessionReplayGuard(session_id=session),
                            handoff=handoff,
                            session_active=lambda: True,
                            asr_released=lambda: True,
                            stop_requested=stopped,
                            clock=time.time, enabled=True,
                        ))
                except (OSError, TimeoutError, ValueError):
                    server_errors.append("server-rejected")
            worker = threading.Thread(
                target=server_worker, name="MyAI-rehearsal-socket",
                daemon=True,
            )
            worker.start()
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(1.0)
                    client.connect(str(endpoint))
                    client_result = exchange_final_over_connected_socket(
                        client, secret=secret, session_id=session,
                        request_id=request, issued_at=issued_at,
                        text=_SYNTHETIC_TRANSCRIPT,
                        expected_peer_uid=uid,
                        reply_guard=OneSessionReplyGuard(session_id=session),
                        session_active=lambda: True,
                        asr_released=lambda: True,
                        stop_requested=stopped, enabled=True,
                        clock=time.time, max_wait_seconds=2.0,
                    )
            finally:
                worker.join(timeout=3.0)
            if worker.is_alive() or server_errors or len(server_reports) != 1:
                return {"status": "server-rehearsal-failed"}

    # TemporaryDirectory has deleted the socket and its private parent.
    # Only the single synthetic test turn can ever produce an answer.
    if (client_result.get("status") == "ready"
            and server_reports[0] == {"status": "sent", "reply_status": "ready"}
            and fake.calls == 1):
        return {
            "status": "test-passed",
            "reply": client_result,
            "private_endpoint_removed": not endpoint.exists(),
        }
    if (client_result.get("status") == "withheld"
            and server_reports[0] == {"status": "sent", "reply_status": "withheld"}
            and fake.calls == 1):
        return {
            "status": "test-withheld",
            "reply": client_result,
            "private_endpoint_removed": not endpoint.exists(),
        }
    return {"status": "rehearsal-rejected"}
