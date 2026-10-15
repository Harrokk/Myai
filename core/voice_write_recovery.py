"""Local, human-operated two-phase release of an unreconciled voice marker.

Not registered as an AI/voice tool. This is deliberately NOT a user
identity credential or an automated exactly-once transaction protocol.
"""
import os
import re
import secrets
import stat

from core.voice_write_journal import (
    BODY, MARKER, VoiceWriteAheadMarker,
)


PENDING = ".voice-write-review-pending.v1"
RECEIPT_PREFIX = "voice-write-reviewed-"
RECEIPT_SUFFIX = ".v1"
TICKET_HEADER = b"MYAI-VOICE-REVIEW-TICKET-v1\n"
TOKEN_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
ATTESTATION_PREFIX = "I VERIFIED EXTERNAL EFFECTS AND STOPPED ALL MYAI WRITERS "


def _read_private(directory, name, expected=None):
    fd = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
        ):
            raise OSError("Unsafe voice recovery file")
        body = os.read(fd, 1025)
        if len(body) > 1024 or (expected is not None and body != expected):
            raise OSError("Unexpected private voice recovery file")
        return body, info
    finally:
        os.close(fd)


def _marker_info(directory):
    return _read_private(directory, MARKER, BODY)[1]


def _ticket_bytes(token, marker):
    return (
        TICKET_HEADER
        + ("token=" + token + "\n").encode("ascii")
        + ("dev=" + str(marker.st_dev) + "\n").encode("ascii")
        + ("inode=" + str(marker.st_ino) + "\n").encode("ascii")
        + ("ctime_ns=" + str(marker.st_ctime_ns) + "\n").encode("ascii")
    )


def _write_private(directory, name, payload):
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600, dir_fd=directory,
    )
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError("Incomplete operator receipt")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory)


class VoiceWriteReconciliation:
    """Operator-only status, prepare and final release; no voice adapter."""

    def __init__(self, project_root):
        self.journal = VoiceWriteAheadMarker(project_root)

    def inspect(self):
        """Return fixed, non-sensitive state without exposing marker data."""
        directory = self.journal._open_directory()
        try:
            with self.journal._locked_directory(directory):
                try:
                    _marker_info(directory)
                except FileNotFoundError:
                    return {"status": "no_marker"}
                try:
                    _read_private(directory, PENDING)
                except FileNotFoundError:
                    return {"status": "needs_external_review"}
                return {"status": "review_ticket_pending"}
        finally:
            os.close(directory)

    def prepare(self):
        """Issue a receipt ticket only; never remove the live block."""
        directory = self.journal._open_directory()
        try:
            with self.journal._locked_directory(directory):
                marker = _marker_info(directory)
                token = secrets.token_hex(16)
                _write_private(directory, PENDING,
                               _ticket_bytes(token, marker))
                return token
        finally:
            os.close(directory)

    def finalize(self, token, acknowledgement):
        """After explicit local attestation, persist receipt before unlock.

        This cannot verify external side effects or prove old worker exit.
        An interrupted release always leaves either the marker blocked or
        a durable review receipt. The operator must enforce process-stop.
        """
        if (not isinstance(token, str)
                or not TOKEN_PATTERN.fullmatch(token)
                or acknowledgement != ATTESTATION_PREFIX + token):
            return False
        directory = self.journal._open_directory()
        try:
            with self.journal._locked_directory(directory):
                marker = _marker_info(directory)
                ticket, _ = _read_private(directory, PENDING)
                if ticket != _ticket_bytes(token, marker):
                    return False
                receipt = RECEIPT_PREFIX + token + RECEIPT_SUFFIX
                # Hard-link no-overwrite prevents replacing old receipts.
                os.link(
                    PENDING, receipt,
                    src_dir_fd=directory, dst_dir_fd=directory,
                    follow_symlinks=False,
                )
                os.fsync(directory)
                # The old pending ticket's link count is now two; it was
                # validated BEFORE linking and no other callers can
                # change these paths while holding the shared lock.
                os.unlink(PENDING, dir_fd=directory)
                os.fsync(directory)
                # Only after receipt durability do we unlock this
                # previously attempted voice write for a *new* core.
                os.unlink(MARKER, dir_fd=directory)
                os.fsync(directory)
                return True
        finally:
            os.close(directory)
