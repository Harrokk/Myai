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


def _read_private(directory, name, expected=None, *, links=1):
    fd = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_nlink != links
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
                    marker = _marker_info(directory)
                except FileNotFoundError:
                    return {"status": "no_marker"}
                try:
                    ticket, _ = _read_private(directory, PENDING)
                except FileNotFoundError:
                    return {"status": "needs_external_review"}
                # A crash immediately after O_EXCL file creation can
                # leave an empty or truncated ticket. Never present it
                # as an actionable, valid operator review.
                match = re.fullmatch(
                    rb"MYAI-VOICE-REVIEW-TICKET-v1\\n"
                    rb"token=([0-9a-f]{32})\\n"
                    rb"dev=[0-9]+\\ninode=[0-9]+\\n"
                    rb"ctime_ns=[0-9]+\\n",
                    ticket,
                )
                if (match is None or ticket != _ticket_bytes(
                    match.group(1).decode("ascii"), marker
                )):
                    raise OSError("Incomplete or stale voice review ticket")
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
                expected = _ticket_bytes(token, marker)
                receipt = RECEIPT_PREFIX + token + RECEIPT_SUFFIX
                # Recover conservatively across a crash at EACH previous
                # release boundary. No release happens without the
                # operator presenting the same ticket and attestation.
                try:
                    try:
                        ticket, ticket_info = _read_private(directory, PENDING)
                    except OSError as error:
                        if not isinstance(error, FileNotFoundError):
                            # Only allow a 2-link ticket if its matching
                            # private receipt exists and has the same inode.
                            ticket, ticket_info = _read_private(
                                directory, PENDING, links=2,
                            )
                            linked, receipt_info = _read_private(
                                directory, receipt, links=2,
                            )
                            if (ticket != expected or linked != expected
                                    or ticket_info.st_dev != receipt_info.st_dev
                                    or ticket_info.st_ino != receipt_info.st_ino):
                                return False
                        else:
                            raise
                except FileNotFoundError:
                    # Crash after removing the pending name, but before
                    # removing the marker. A durable, private receipt
                    # bound to THIS marker must still exist.
                    saved, _ = _read_private(directory, receipt, links=1)
                    if saved != expected:
                        return False
                else:
                    if ticket != expected:
                        return False
                    if ticket_info.st_nlink == 1:
                        # Normal case: create a no-overwrite receipt, then
                        # sync it BEFORE releasing the marker.
                        os.link(
                            PENDING, receipt,
                            src_dir_fd=directory, dst_dir_fd=directory,
                            follow_symlinks=False,
                        )
                    elif ticket_info.st_nlink != 2:
                        raise OSError("Unexpected pending ticket links")
                    os.fsync(directory)
                    os.unlink(PENDING, dir_fd=directory)
                    os.fsync(directory)
                # A receipt exists and the pending name is gone. This
                # is the ONLY permitted point for unmarking an effect.
                os.unlink(MARKER, dir_fd=directory)
                os.fsync(directory)
                return True
        finally:
            os.close(directory)
