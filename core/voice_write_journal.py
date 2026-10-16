"""Fail-closed, crash-durable marker before effectful voice tool callbacks.

No user content, tool names, paths, tokens, HMACs or raw results are stored.
A conservative single marker also blocks a second write after a success
until explicit out-of-band state reconciliation. Never auto-remove on exit.
"""
import os
from contextlib import contextmanager
from pathlib import Path
import stat

try:
    import fcntl
except ImportError:  # Windows must fail closed for effectful voice writes.
    fcntl = None


MARKER = "voice-write-unreconciled.v1"
BODY = b"MYAI-VOICE-WRITE-UNRECONCILED-v1\n"
RUNTIME = "runtime"
LOCK = ".voice-write-safety.lock.v1"
ACTIVE_LOCK = ".voice-active-writer.lock.v1"


class VoiceWriteAheadMarker:
    """A single durable, never-auto-cleared marker per project directory.

    Exclusive creation provides cross-process refusal when all invocations
    use the same project root and trusted, local POSIX filesystem.
    """

    def __init__(self, project_root):
        self.root = Path(project_root)
        self._blocked = False

    def _open_directory(self):
        # Windows/unsupported local filesystems do not expose this POSIX
        # dirfd+no-follow protocol. Deny voice writes rather than falling
        # back to an unsafe non-exclusive path operation.
        if not (
            fcntl is not None
            and hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and hasattr(os, "geteuid")
            and os.mkdir in os.supports_dir_fd
            and os.stat in os.supports_dir_fd
        ):
            raise OSError("Durable voice marker unsupported on this platform")
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

    @contextmanager
    def _locked_directory(self, directory):
        """Serialize cooperative writers and operator reconciliation.

        Never unlink or replace the lock itself: its inode must remain
        stable across process restarts and marker releases.
        """
        fd = os.open(
            LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600, dir_fd=directory,
        )
        try:
            details = os.fstat(fd)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.geteuid()
                or details.st_mode & 0o077
                or details.st_nlink != 1
            ):
                raise OSError("Untrusted voice journal lock")
            # Make the stable lock inode directory entry durable before
            # relying on flock for future cooperating writer processes.
            os.fsync(directory)
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _active_lock_fd(self, directory):
        """Open the stable, private writer-presence flock inode.

        This is a lease for *live cooperating processes*, not a proof of
        the absence of detached grandchildren or external side effects.
        """
        fd = os.open(
            ACTIVE_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600, dir_fd=directory,
        )
        try:
            details = os.fstat(fd)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.geteuid()
                or details.st_mode & 0o077
                or details.st_nlink != 1
            ):
                raise OSError("Untrusted active writer lock")
            os.fsync(directory)
            return fd
        except BaseException:
            os.close(fd)
            raise

    @contextmanager
    def active_writer(self):
        """Hold a shared interprocess lease through the *entire* callback.

        Finalize holds the existing journal mutex and attempts an
        exclusive NONBLOCKING lease before removing a write marker.
        """
        directory = self._open_directory()
        try:
            fd = self._active_lock_fd(directory)
            try:
                # Never wait behind an operator in the middle of a
                # reviewed release; deny this stale voice invocation.
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                try:
                    yield
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        finally:
            os.close(directory)

    @contextmanager
    def require_quiescent_writers(self, directory):
        """Fail closed if a *participating* writer still owns a lease.

        Called only while the stable journal lock is already held.
        This does NOT attest the absence of uncooperative OS processes.
        """
        fd = self._active_lock_fd(directory)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise OSError("Active cooperating voice writer") from error
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    @property
    def review_required(self):
        if self._blocked:
            return True
        try:
            directory = self._open_directory()
            try:
                with self._locked_directory(directory):
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
                with self._locked_directory(directory):
                    # No separate-process writer may race the last check
                    # and marker creation while using this lock protocol.
                    try:
                        os.stat(MARKER, dir_fd=directory,
                                follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        self._blocked = True
                        return False
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
