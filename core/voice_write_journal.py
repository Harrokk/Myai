"""Fail-closed, crash-durable marker before effectful voice tool callbacks.

No user content, tool names, paths, tokens, HMACs or raw results are stored.
A conservative single marker also blocks a second write after a success
until explicit out-of-band state reconciliation. Never auto-remove on exit.
"""
import os
from pathlib import Path
import stat


MARKER = "voice-write-unreconciled.v1"
BODY = b"MYAI-VOICE-WRITE-UNRECONCILED-v1\n"
RUNTIME = "runtime"


class VoiceWriteAheadMarker:
    """A single durable, never-auto-cleared marker per project directory.

    Exclusive creation provides cross-process refusal when all invocations
    use the same project root and trusted, local POSIX filesystem.
    """

    def __init__(self, project_root):
        self.root = Path(project_root)
        self._blocked = False

    def _open_directory(self):
        # Fail closed on errors and symlinks; never create an arbitrary
        # destination supplied by a transcript or a tool argument.
        rootfd = os.open(
            self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            try:
                os.mkdir(RUNTIME, mode=0o700, dir_fd=rootfd)
                os.fsync(rootfd)
            except FileExistsError:
                pass
            directory = os.open(
                RUNTIME,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=rootfd,
            )
            try:
                details = os.fstat(directory)
                if (
                    not stat.S_ISDIR(details.st_mode)
                    or details.st_uid != os.geteuid()
                    or details.st_mode & 0o022
                ):
                    raise OSError("Untrusted voice journal directory")
                return directory
            except BaseException:
                os.close(directory)
                raise
        finally:
            os.close(rootfd)

    @property
    def review_required(self):
        if self._blocked:
            return True
        try:
            directory = self._open_directory()
            try:
                try:
                    os.stat(MARKER, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    return False
                self._blocked = True
                return True
            finally:
                os.close(directory)
        except (OSError, ValueError, TypeError):
            # Cannot verify durable state -> never authorize a write.
            self._blocked = True
            return True

    def begin_effect(self):
        """Return True only after a private, durable exclusive marker exists.

        The marker is intentionally retained even after successful return:
        external delivery, success receipts and side effects are not atomic.
        """
        if self.review_required:
            return False
        try:
            directory = self._open_directory()
            try:
                flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW)
                descriptor = os.open(
                    MARKER, flags, 0o600, dir_fd=directory
                )
                try:
                    written = os.write(descriptor, BODY)
                    if written != len(BODY):
                        raise OSError("Incomplete private marker")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.fsync(directory)
                self._blocked = True
                return True
            finally:
                os.close(directory)
        except (OSError, ValueError, TypeError):
            self._blocked = True
            return False
