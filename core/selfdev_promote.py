import json
import errno
import hmac
import hashlib
import re
import stat
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import time
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # Windows development can still use msvcrt byte locks.
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

from core.audit_log import (
    AuditLogger,
    audit_outcome_for_exception,
)
from core.selfdev_workspace import (
    SelfDevWorkspace,
    _sha256,
    _allowed_relative_path,
)


def _safe_identifier(
    value,
):
    identifier = str(
        value
    )

    if (
        not identifier
        or len(
            identifier
        ) > 96
        or any(
            character
            not in (
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789_-"
            )
            for character
            in identifier
        )
    ):
        raise ValueError(
            "Ogiltigt promotion-ID."
        )

    return identifier


def _read_json(path):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def _sync_directory(path):
    """Best-effort durable directory entry flush on POSIX filesystems."""
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(
        str(path),
        os.O_RDONLY | os.O_DIRECTORY,
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _pinned_parent(path, *, create=False):
    """Traverse all parents from / using no-follow dirfd opens.

    No pathname is re-resolved to select the parent of an active-code
    replacement. The operator controls the root path and its ownership.
    """
    if not all(hasattr(os, attr) for attr in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise RuntimeError("Säker selfdev-promotion kräver Linux dir_fd.")
    target = Path(path)
    if not target.is_absolute() or ".." in target.parts:
        raise PermissionError("Säker promotion kräver en absolut tillåten sökväg.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    directory_fd = os.open("/", flags)
    try:
        for name in target.parts[1:-1]:
            if create:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=directory_fd)
                except FileExistsError:
                    pass
            new_fd = os.open(name, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = new_fd
        yield directory_fd, target.name
    finally:
        os.close(directory_fd)


def _source_matches_before_replace(destination, expected, *, directory_fd):
    """Check pinned target's exact bytes without following target symlinks."""
    if expected is _NO_EXPECTED_SOURCE:
        return
    filename = Path(destination).name
    if expected is None:
        try:
            os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise RuntimeError("Extern ändring: ny målkodsfil finns redan.")

    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(filename, flags, dir_fd=directory_fd)
    except OSError as error:
        raise RuntimeError(
            "Extern ändring av källkodsfil; promotion avbröts."
        ) from error
    try:
        from core.selfdev_workspace import _hash_pinned_regular_file
        observed = _hash_pinned_regular_file(fd)
    except (OSError, PermissionError, RuntimeError) as error:
        raise RuntimeError(
            "Extern ändring av källkodsfil; promotion avbröts."
        ) from error
    finally:
        os.close(fd)
    if observed != expected:
        raise RuntimeError(
            "Extern ändring av källkodsfil; promotion avbröts."
        )


_NO_EXPECTED_SOURCE = object()


def _atomic_copy(
    source, destination, *,
    expected_old=_NO_EXPECTED_SOURCE,
    expected_source=None,
):
    """Copy from pinned source to pinned destination, validating before rename."""
    source = Path(source)
    destination = Path(destination)
    with _pinned_parent(source) as (source_parent_fd, source_name):
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        source_fd = os.open(source_name, flags, dir_fd=source_parent_fd)
        try:
            source_info = os.fstat(source_fd)
            if not stat.S_ISREG(source_info.st_mode):
                raise PermissionError("Promotion-källfilen är inte en vanlig fil.")

            with _pinned_parent(destination, create=True) as (
                target_parent_fd, target_name
            ):
                temporary = (
                    "." + target_name + "." + secrets.token_hex(12) + ".tmp"
                )
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                flags |= getattr(os, "O_CLOEXEC", 0)
                target_fd = os.open(
                    temporary, flags, 0o600, dir_fd=target_parent_fd
                )
                try:
                    digest = hashlib.sha256()
                    bytes_read = 0
                    while True:
                        piece = os.read(source_fd, 65_536)
                        if not piece:
                            break
                        digest.update(piece)
                        bytes_read += len(piece)
                        view = memoryview(piece)
                        while view:
                            written = os.write(target_fd, view)
                            if written <= 0:
                                raise OSError("Promotion-kopiering kunde inte slutföras.")
                            view = view[written:]

                    after = os.fstat(source_fd)
                    if (
                        bytes_read != source_info.st_size
                        or after.st_dev != source_info.st_dev
                        or after.st_ino != source_info.st_ino
                        or after.st_size != source_info.st_size
                        or after.st_mtime_ns != source_info.st_mtime_ns
                        or after.st_ctime_ns != source_info.st_ctime_ns
                    ):
                        raise RuntimeError(
                            "Källfilen ändrades under promotion-kopieringen."
                        )
                    if (
                        expected_source is not None
                        and digest.hexdigest() != expected_source
                    ):
                        raise RuntimeError(
                            "Källfil i staging har ändrats efter verifiering."
                        )
                    os.fchmod(
                        target_fd, stat.S_IMODE(source_info.st_mode) & 0o777
                    )
                    os.fsync(target_fd)
                    os.close(target_fd)
                    target_fd = -1

                    _source_matches_before_replace(
                        destination, expected_old, directory_fd=target_parent_fd
                    )
                    # Descriptor-relative rename never follows a swapped
                    # intermediate symlink or final target link.
                    os.replace(
                        temporary, target_name,
                        src_dir_fd=target_parent_fd,
                        dst_dir_fd=target_parent_fd,
                    )
                    os.fsync(target_parent_fd)
                    # Preserve the existing failure-injection/durability hook
                    # used by promotion and rollback regression tests.
                    _sync_directory(destination.parent)
                except BaseException:
                    if target_fd >= 0:
                        os.close(target_fd)
                    try:
                        os.unlink(temporary, dir_fd=target_parent_fd)
                    except FileNotFoundError:
                        pass
                    raise
        finally:
            os.close(source_fd)


def _hash_existing_regular_path(path):
    """Hash the current allowed regular file using no-follow parent handles."""
    from core.selfdev_workspace import _hash_pinned_regular_file

    with _pinned_parent(path) as (parent_fd, name):
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        file_fd = os.open(name, flags, dir_fd=parent_fd)
        try:
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PermissionError("Osäker källfil vid backupkontroll.")
            return _hash_pinned_regular_file(file_fd)
        finally:
            os.close(file_fd)


def _copy_verified_backup(source, destination):
    """Stage a private backup of one pinned active source inode.

    Return SHA-256 of the exact bytes copied to the private backup.
    Abort and unlink a partial backup on source mutation or I/O failure.
    """
    with _pinned_parent(source) as (source_parent_fd, source_name):
        source_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        source_flags |= getattr(os, "O_CLOEXEC", 0)
        source_fd = os.open(source_name, source_flags, dir_fd=source_parent_fd)
        try:
            before = os.fstat(source_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise PermissionError("Backup kräver en vanlig källfil utan hårdlänkar.")

            with _pinned_parent(destination, create=True) as (dest_parent_fd, name):
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                flags |= getattr(os, "O_CLOEXEC", 0)
                dest_fd = os.open(name, flags, 0o600, dir_fd=dest_parent_fd)
                try:
                    digest = hashlib.sha256()
                    copied = 0
                    while True:
                        piece = os.read(source_fd, 65_536)
                        if not piece:
                            break
                        digest.update(piece)
                        copied += len(piece)
                        remaining = memoryview(piece)
                        while remaining:
                            written = os.write(dest_fd, remaining)
                            if written <= 0:
                                raise OSError("Säkerhetskopian kunde inte skrivas.")
                            remaining = remaining[written:]

                    after = os.fstat(source_fd)
                    if (
                        copied != before.st_size
                        or after.st_dev != before.st_dev
                        or after.st_ino != before.st_ino
                        or after.st_size != before.st_size
                        or after.st_mtime_ns != before.st_mtime_ns
                        or after.st_ctime_ns != before.st_ctime_ns
                    ):
                        raise RuntimeError("Extern ändring under säkerhetskopiering.")
                    os.fchmod(dest_fd, stat.S_IMODE(before.st_mode) & 0o777)
                    os.fsync(dest_fd)
                    os.close(dest_fd)
                    dest_fd = -1
                    os.fsync(dest_parent_fd)
                    return digest.hexdigest()
                except BaseException:
                    if dest_fd >= 0:
                        os.close(dest_fd)
                    try:
                        os.unlink(name, dir_fd=dest_parent_fd)
                    except FileNotFoundError:
                        pass
                    raise
        finally:
            os.close(source_fd)


def _atomic_write_record(path, record):
    """Publish a complete bounded recovery journal within a pinned dirfd."""
    path = Path(path)
    encoded = (
        json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    if len(encoded) > 1024 * 1024:
        raise ValueError("Återställningsjournalen är för stor.")

    with _pinned_parent(path, create=True) as (directory_fd, name):
        try:
            existing = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        if existing is not None and (
            not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1
        ):
            raise PermissionError("Osäker journalfil i selfdev.")

        temporary = "." + name + "." + secrets.token_hex(12) + ".tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        file_fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(file_fd, "wb") as handle:
                file_fd = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                current = os.stat(
                    name, dir_fd=directory_fd, follow_symlinks=False
                )
            except FileNotFoundError:
                current = None
            if (
                (existing is None) != (current is None)
                or (
                    current is not None and (
                        not stat.S_ISREG(current.st_mode)
                        or current.st_nlink != 1
                        or existing.st_dev != current.st_dev
                        or existing.st_ino != current.st_ino
                    )
                )
            ):
                raise PermissionError("Journalfilen byttes före publicering.")

            os.replace(
                temporary, name,
                src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
            )
            os.fsync(directory_fd)
        except BaseException:
            if file_fd >= 0:
                os.close(file_fd)
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise


class SelfDevPromotionManager:
    def __init__(
        self,
        workspace,
        settings,
        *,
        promotion_id_factory=None,
        audit_logger=None,
    ):
        if not isinstance(
            workspace,
            SelfDevWorkspace,
        ):
            raise TypeError(
                "workspace måste vara en SelfDevWorkspace."
            )

        self.workspace = workspace
        self.settings = settings
        self.config = settings.get(
            "selfdev",
            {},
        )
        self.promotion_id_factory = (
            promotion_id_factory
            or (
                lambda: (
                    time.strftime(
                        "%Y%m%dT%H%M%SZ",
                        time.gmtime(),
                    )
                    + "-"
                    + secrets.token_hex(
                        4
                    )
                )
            )
        )
        self.audit_logger = (
            audit_logger
            or AuditLogger(
                settings,
                workspace.project_root,
            )
        )

    def _private_selfdev_directory(self, *, create=False):
        """Validate (and optionally create) the private directory via dirfds.

        Avoid resolving mutable parent pathnames separately for mkdir, stat
        and ownership checks. Only the trusted project-root spelling is
        returned; callers performing I/O must independently pin their FDs.
        """
        runtime = self.workspace.project_root / "runtime"
        directory = runtime / "selfdev"
        directory_flags = (
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )

        try:
            with _pinned_parent(directory, create=create) as (
                runtime_fd, name
            ):
                runtime_info = os.fstat(runtime_fd)
                if (
                    not stat.S_ISDIR(runtime_info.st_mode)
                    or runtime_info.st_uid != os.geteuid()
                    or runtime_info.st_mode & 0o022
                ):
                    raise PermissionError(
                        "Selfdev-katalogen har osäkra behörigheter."
                    )

                if create:
                    try:
                        os.mkdir(name, mode=0o700, dir_fd=runtime_fd)
                    except FileExistsError:
                        pass

                selfdev_fd = os.open(
                    name, directory_flags, dir_fd=runtime_fd
                )
                try:
                    private_info = os.fstat(selfdev_fd)
                    if (
                        not stat.S_ISDIR(private_info.st_mode)
                        or private_info.st_uid != os.geteuid()
                        or private_info.st_mode & 0o022
                    ):
                        raise PermissionError(
                            "Selfdev-katalogen har osäkra behörigheter."
                        )
                    current = os.stat(
                        name, dir_fd=runtime_fd, follow_symlinks=False
                    )
                    if (
                        not stat.S_ISDIR(current.st_mode)
                        or current.st_dev != private_info.st_dev
                        or current.st_ino != private_info.st_ino
                    ):
                        raise PermissionError(
                            "Selfdev-katalogen ändrades under kontroll."
                        )
                finally:
                    os.close(selfdev_fd)
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.ENOTDIR):
                raise PermissionError(
                    "Selfdev-katalogen får inte vara symlink."
                ) from error
            raise
        return directory

    @contextmanager
    def _project_mutation_lock(self):
        """Nonblocking OS lock shared by all selfdev sessions for a project.

        The kernel releases advisory locks if the process crashes. Other
        non-cooperating filesystem writers are outside this protection.
        """
        lock_dir = self._private_selfdev_directory(create=True)
        lock_path = lock_dir / ".promotion.lock"
        flags = (
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        flags |= getattr(os, "O_BINARY", 0)
        # A symlink swap of runtime/selfdev between the preflight and this
        # open must not select an external lock. Pin every parent component.
        with _pinned_parent(lock_path) as (directory_fd, lock_name):
            parent = os.fstat(directory_fd)
            if (
                not stat.S_ISDIR(parent.st_mode)
                or parent.st_uid != os.geteuid()
                or parent.st_mode & 0o022
            ):
                raise PermissionError(
                    "Selfdev-katalogen har osäkra behörigheter."
                )
            descriptor = os.open(
                lock_name, flags, 0o600, dir_fd=directory_fd
            )
        acquired = False
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or (os.name == "posix" and (
                    metadata.st_uid != os.geteuid()
                    or (metadata.st_mode & 0o077)
                ))
            ):
                raise PermissionError("Osäker selfdev-projektlåsfil.")
            if fcntl is not None:
                try:
                    fcntl.flock(
                        descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                except BlockingIOError as error:
                    raise RuntimeError(
                        "En annan selfdev-uppdatering pågår i projektet."
                    ) from error
            elif msvcrt is not None:
                try:
                    if os.fstat(descriptor).st_size == 0:
                        os.write(descriptor, b"0")
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise RuntimeError(
                        "En annan selfdev-uppdatering pågår i projektet."
                    ) from error
            else:
                raise RuntimeError("Operativsystemet saknar säkert selfdev-lås.")
            acquired = True
            yield
        finally:
            if acquired:
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                else:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            os.close(descriptor)

    def _journal_integrity_key(self, *, create=False):
        """Read/publish the 32-byte project HMAC key under one pinned dirfd.

        The private-directory preflight remains for compatibility, but all
        security-sensitive operations use the same no-follow parent inode.
        """
        directory = self._private_selfdev_directory(create=create)
        key_path = directory / ".journal-integrity-key"
        with _pinned_parent(key_path) as (directory_fd, filename):
            parent_info = os.fstat(directory_fd)
            if (
                not stat.S_ISDIR(parent_info.st_mode)
                or parent_info.st_uid != os.geteuid()
                or parent_info.st_mode & 0o022
            ):
                raise PermissionError(
                    "Selfdev-katalogen har osäkra behörigheter."
                )

            if create:
                temporary = ".journal-key." + secrets.token_hex(12)
                flags = (
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0)
                )
                try:
                    temp_fd = os.open(
                        temporary, flags, 0o600, dir_fd=directory_fd
                    )
                except OSError:
                    raise
                try:
                    with os.fdopen(temp_fd, "wb") as handle:
                        handle.write(secrets.token_bytes(32))
                        handle.flush()
                        os.fsync(handle.fileno())
                    try:
                        os.link(
                            temporary, filename,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        # The existing key will be verified below. Never
                        # replace or regenerate a key which already exists.
                        pass
                    else:
                        os.fsync(directory_fd)
                finally:
                    os.unlink(temporary, dir_fd=directory_fd)
                    os.fsync(directory_fd)

            flags = (
                os.O_RDONLY | os.O_NOFOLLOW
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            try:
                descriptor = os.open(filename, flags, dir_fd=directory_fd)
            except OSError as error:
                raise RuntimeError(
                    "Selfdev-integritetsnyckeln saknas eller kan inte läsas."
                ) from error
            with os.fdopen(descriptor, "rb") as handle:
                before = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                    or before.st_uid != os.geteuid()
                    or before.st_mode & 0o077
                    or before.st_size != 32
                ):
                    raise RuntimeError("Osäker selfdev-integritetsnyckel.")
                secret = handle.read(33)
                after = os.fstat(handle.fileno())
                if (
                    len(secret) != 32
                    or after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or after.st_ctime_ns != before.st_ctime_ns
                    or after.st_ino != before.st_ino
                    or after.st_dev != before.st_dev
                ):
                    raise RuntimeError("Ogiltig selfdev-integritetsnyckel.")
                return secret

    def _write_journal(self, path, record):
        if not isinstance(record, dict):
            raise RuntimeError("Ogiltig återställningsjournal.")
        copy = dict(record)
        copy.pop("journal_hmac", None)
        copy["journal_version"] = 1
        payload = json.dumps(
            copy, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        copy["journal_hmac"] = hmac.new(
            self._journal_integrity_key(create=True),
            payload, hashlib.sha256,
        ).hexdigest()
        _atomic_write_record(path, copy)

    @staticmethod
    def _read_recovery_json(path, *, include_raw=False):
        """Bounded, single-inode, strictly decoded read of recovery records."""
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        try:
            with _pinned_parent(Path(path)) as (directory_fd, name):
                descriptor = os.open(name, flags, dir_fd=directory_fd)
                with os.fdopen(descriptor, "rb") as handle:
                    before = os.fstat(handle.fileno())
                    if (
                        not stat.S_ISREG(before.st_mode)
                        or before.st_nlink != 1
                        or before.st_size > 1024 * 1024
                    ):
                        raise RuntimeError(
                            "Osäker eller för stor återställningsjournal."
                        )
                    content = handle.read(1024 * 1024 + 1)
                    after = os.fstat(handle.fileno())
                    if (
                        before.st_dev != after.st_dev
                        or before.st_ino != after.st_ino
                        or before.st_size != after.st_size
                        or before.st_mtime_ns != after.st_mtime_ns
                        or before.st_ctime_ns != after.st_ctime_ns
                        or len(content) != before.st_size
                    ):
                        raise RuntimeError(
                            "Återställningsjournalen ändrades under läsning."
                        )
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise RuntimeError(
                    "Återställningsjournalen är en symlink."
                ) from error
            raise RuntimeError("Återställningsjournalen kan inte läsas.") from error
        if len(content) > 1024 * 1024:
            raise RuntimeError("Återställningsjournalen är för stor.")

        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Dubbla fältnamn i journalen.")
                result[key] = value
            return result

        def invalid_constant(value):
            raise ValueError("Ej ändligt numeriskt värde i journalen.")

        try:
            parsed = json.loads(
                content.decode("utf-8"),
                object_pairs_hook=unique_pairs,
                parse_constant=invalid_constant,
            )
            return (parsed, content) if include_raw else parsed
        except (UnicodeError, ValueError, RecursionError) as error:
            raise RuntimeError("Återställningsjournalens JSON är ogiltig.") from error

    def _read_journal(self, path):
        record = self._read_recovery_json(path)
        if not isinstance(record, dict) or record.get("journal_version") != 1:
            raise RuntimeError("Återställningsjournal saknar integritetsskydd.")
        signature = record.get("journal_hmac")
        if not isinstance(signature, str) or len(signature) != 64:
            raise RuntimeError("Återställningsjournalens integritet är ogiltig.")
        unsigned = dict(record)
        unsigned.pop("journal_hmac")
        try:
            payload = json.dumps(
                unsigned, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Återställningsjournalens innehåll är ogiltigt."
            ) from error
        computed = hmac.new(
            self._journal_integrity_key(), payload, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, computed):
            raise RuntimeError(
                "Återställningsjournalens integritet kunde inte verifieras."
            )
        return record

    def _require_promotion_enabled(self):
        if not self.config.get(
            "enabled",
            False,
        ):
            raise PermissionError(
                "Selfdev är avstängt i konfigurationen."
            )

        if not self.config.get(
            "promotion_enabled",
            False,
        ):
            raise PermissionError(
                "Selfdev-promotion är avstängd i konfigurationen."
            )

    def _verification(self):
        try:
            data = self.workspace.read_verification()
        except FileNotFoundError as error:
            raise RuntimeError(
                "Selfdev-sessionen saknar verifieringsresultat."
            ) from error

        if not data.get(
            "passed",
            False,
        ):
            raise RuntimeError(
                "Selfdev-verifieringen är inte godkänd."
            )

        if data.get(
            "sandbox"
        ) != "bubblewrap":
            raise RuntimeError(
                "Promotion kräver Bubblewrap-verifiering."
            )

        if not data.get(
            "network_isolated",
            False,
        ):
            raise RuntimeError(
                "Promotion kräver nätverksisolerad verifiering."
            )

        if data.get(
            "host_devices_exposed",
            True,
        ):
            raise RuntimeError(
                "Promotion kräver verifiering utan host-enheter."
            )

        return data

    def _safe_project_target(
        self,
        relative,
    ):
        relative = Path(relative)
        if not _allowed_relative_path(relative):
            raise PermissionError("Otillåten källkodsfil i promotion-journalen.")
        root = (
            self.workspace
            .project_root
        )
        target = (
            root
            / relative
        )

        try:
            target.resolve(
                strict=False
            ).relative_to(
                root.resolve()
            )
        except ValueError as error:
            raise PermissionError(
                "Promotion försökte lämna projektroten."
            ) from error

        current = root

        for part in Path(
            relative
        ).parts[:-1]:
            current = (
                current
                / part
            )

            if current.is_symlink():
                raise PermissionError(
                    "Promotion genom symlink är inte tillåten."
                )

        if target.is_symlink():
            raise PermissionError(
                "Promotion till symlink är inte tillåten."
            )

        return target

    def _require_no_interrupted_promotion(self):
        # An interrupted update in *any* known session cannot be covered
        # by a new update in another session.
        sources = {
            self.workspace.project_root / "runtime" / "selfdev",
            self.workspace.session_root.parent,
        }
        for sessions_root in sources:
            if not sessions_root.exists():
                continue
            if sessions_root.is_symlink():
                raise RuntimeError("Selfdev-sessionkatalogen är en symlink.")
            for session_root in sessions_root.iterdir():
                if session_root.is_symlink():
                    raise RuntimeError("Otillåten selfdev-sessionsymlink.")
                if not session_root.is_dir():
                    continue
                journal_dir = session_root / "rollbacks"
                if journal_dir.is_symlink():
                    raise RuntimeError("Otillåten selfdev-rollbacksymlink.")
                if not journal_dir.exists():
                    continue
                for candidate in journal_dir.iterdir():
                    if candidate.is_symlink():
                        raise RuntimeError("Otillåten selfdev-journalsymlink.")
                    if not candidate.is_dir():
                        continue
                    record_path = candidate / "promotion.json"
                    if not record_path.is_file() or record_path.is_symlink():
                        raise RuntimeError(
                            "Ofullständig selfdev-promotion saknar återställningsjournal."
                        )
                    try:
                        record = self._read_journal(record_path)
                    except (OSError, ValueError, TypeError, RuntimeError) as error:
                        raise RuntimeError(
                            "Selfdev-promotion har en skadad återställningsjournal."
                        ) from error
                    if not isinstance(record, dict):
                        raise RuntimeError("Ogiltig återställningsjournal.")
                    status = record.get("state")
                    if status in {"completed", "recovered", "reverted"}:
                        continue
                    if status is None and record.get("promoted_unix_time"):
                        continue
                    raise RuntimeError(
                        "Ofullständig selfdev-promotion måste återställas manuellt."
                    )

    def _preflight_promotion(
        self,
    ):
        verification = (
            self._verification()
        )
        changes = (
            self.workspace
            .changed_files()
        )

        if changes[
            "deleted"
        ]:
            raise RuntimeError(
                "Filradering stöds inte i selfdev-promotion."
            )

        if (
            changes[
                "manifest_digest"
            ]
            != verification.get(
                "workspace_manifest_digest"
            )
        ):
            raise RuntimeError(
                "Selfdev-workspacen har ändrats efter verifieringen."
            )

        drift = (
            self.workspace
            .source_drift()
        )

        if drift:
            raise RuntimeError(
                "Aktiv källkod har ändrats sedan selfdev-sessionen skapades: "
                + ", ".join(
                    drift
                )
            )

        changed = (
            changes[
                "changed"
            ]
            + changes[
                "added"
            ]
        )

        if not changed:
            raise RuntimeError(
                "Selfdev-sessionen innehåller inga ändringar."
            )

        return (
            verification,
            changes,
            sorted(
                changed
            ),
        )

    def promote(
        self,
        approval_phrase,
    ):
        target = (
            "selfdev/"
            + self.workspace.session_id
        )
        self.audit_logger.write_attempt(
            action="selfdev_promote",
            component="selfdev",
            target=target,
            details={
                "session_id": (
                    self.workspace.session_id
                ),
            },
        )

        try:
            with self._project_mutation_lock():
                record = self._promote_impl(
                    approval_phrase
                )
        except Exception as error:
            self.audit_logger.write_result(
                action="selfdev_promote",
                component="selfdev",
                outcome=(
                    audit_outcome_for_exception(
                        error
                    )
                ),
                target=target,
                details={
                    "session_id": (
                        self.workspace.session_id
                    ),
                    "error_type": type(
                        error
                    ).__name__,
                },
            )
            raise

        self.audit_logger.write_result(
            action="selfdev_promote",
            component="selfdev",
            outcome="success",
            target=target,
            details={
                "session_id": (
                    self.workspace.session_id
                ),
                "promotion_id": record.get(
                    "promotion_id"
                ),
                "changed_count": len(
                    record.get(
                        "changed",
                        [],
                    )
                ),
                "added_count": len(
                    record.get(
                        "added",
                        [],
                    )
                ),
            },
        )
        return record

    def _promote_impl(self, approval_phrase):
        self._require_promotion_enabled()
        expected = "PROMOTE " + self.workspace.session_id
        if str(approval_phrase) != expected:
            raise PermissionError("Fel manuell promotion-frase.")

        self._require_no_interrupted_promotion()
        verification, changes, paths = self._preflight_promotion()
        promotion_id = _safe_identifier(self.promotion_id_factory())
        rollback_root = (
            self.workspace.session_root / "rollbacks" / promotion_id
        )
        if rollback_root.exists():
            raise FileExistsError("Promotion-ID finns redan.")
        # Private backup metadata, including originally world-readable code.
        rollback_root.mkdir(parents=True, exist_ok=False, mode=0o700)

        # Make parent directory entries durable before relying on a
        # journal stored under this newly created promotion directory.
        _sync_directory(rollback_root.parent)
        _sync_directory(rollback_root.parent.parent)
        backups = {}
        planned_hashes = {}
        try:
            for relative in paths:
                source = self.workspace.workspace_root / relative
                target = self._safe_project_target(relative)
                planned_hashes[relative] = changes["manifest"][relative]
                if _sha256(source) != planned_hashes[relative]:
                    raise RuntimeError(
                        "Källfil i staging har ändrats efter verifiering."
                    )
                if target.exists():
                    backup = self._safe_backup_path(rollback_root, relative)
                    # Hash exactly the bytes copied from one pinned active
                    # inode, then re-open the active name without following
                    # symlinks before preparing the rollback journal.
                    old_digest = _copy_verified_backup(target, backup)
                    if _hash_existing_regular_path(target) != old_digest:
                        raise RuntimeError(
                            "Extern ändring under säkerhetskopiering."
                        )
                    backups[relative] = {
                        "existed": True,
                        "sha256": old_digest,
                    }
                else:
                    backups[relative] = {"existed": False, "sha256": None}
            # Ensure nested backup directory entries reach stable storage.
            for current_dir in sorted(
                {parent for parent in (rollback_root / "files").rglob("*")
                 if parent.is_dir()},
                key=lambda p: len(p.parts),
                reverse=True,
            ) if (rollback_root / "files").exists() else ():
                _sync_directory(current_dir)
            _sync_directory(rollback_root)
        except BaseException:
            # No active file has been modified before the journal is
            # prepared; remove an unusable partial backup safely.
            shutil.rmtree(rollback_root)
            _sync_directory(rollback_root.parent)
            raise

        journal = {
            "session_id": self.workspace.session_id,
            "promotion_id": promotion_id,
            "state": "prepared",
            "verification_manifest_digest": verification[
                "workspace_manifest_digest"
            ],
            "changed": changes["changed"],
            "added": changes["added"],
            "backups": backups,
            "planned_hashes": planned_hashes,
            "after_hashes": {},
            "rolled_back": False,
        }
        record_path = rollback_root / "promotion.json"
        # Power loss after this write can be recovered via the backups and
        # intended content hashes. No active file is touched before this.
        self._write_journal(record_path, journal)

        applied = []
        after_hashes = {}
        try:
            for relative in paths:
                source = self.workspace.workspace_root / relative
                target = self._safe_project_target(relative)
                if _sha256(source) != planned_hashes[relative]:
                    raise RuntimeError(
                        "Källfil i staging har ändrats efter verifiering."
                    )
                # Include current target before copying so a rename followed
                # by a failed fsync still leaves a recoverable PREPARED record.
                applied.append(relative)
                _atomic_copy(
                    source, target,
                    expected_old=backups[relative]["sha256"],
                    expected_source=planned_hashes[relative],
                )
                after_hashes[relative] = _sha256(target)
                if after_hashes[relative] != planned_hashes[relative]:
                    raise RuntimeError(
                        "Promoterad kodfil matchar inte verifierad version."
                    )

            record = {
                **journal,
                "state": "completed",
                "promoted_unix_time": time.time(),
                "after_hashes": after_hashes,
            }
            self._write_journal(record_path, record)
        except Exception:
            # Restore only known before/after versions. If an external
            # writer changed *any* touched file, leave PREPARED for
            # explicit manual recovery rather than clobber their work.
            to_restore = []
            for relative in applied:
                target = self._safe_project_target(relative)
                original = backups[relative]["sha256"]
                desired = planned_hashes[relative]
                if target.is_symlink():
                    raise RuntimeError(
                        "Extern filändring under promotion; manuell återställning krävs."
                    )
                if not os.path.lexists(target):
                    if original is not None:
                        raise RuntimeError(
                            "Extern filändring under promotion; manuell återställning krävs."
                        )
                    continue
                observed = _sha256(target)
                if observed not in {original, desired}:
                    raise RuntimeError(
                        "Extern filändring under promotion; manuell återställning krävs."
                    )
                if observed != original:
                    to_restore.append(relative)
            self._restore_from_backup(
                rollback_root, backups, to_restore,
                expected_after=planned_hashes,
            )
            self._write_journal(
                record_path,
                {
                    **journal,
                    "state": "reverted",
                    "rolled_back": True,
                    "reverted_unix_time": time.time(),
                },
            )
            raise

        return record

    def _safe_backup_path(
        self,
        rollback_root,
        relative,
    ):
        if not _allowed_relative_path(relative):
            raise PermissionError("Otillåten backup-sökväg.")
        root = Path(rollback_root)
        if root.is_symlink():
            raise PermissionError("Rollback-roten får inte vara symlink.")
        base = root / "files"
        if base.is_symlink():
            raise PermissionError("Backup-roten får inte vara symlink.")
        current = base
        for part in Path(relative).parts:
            current = current / part
            if current.is_symlink():
                raise PermissionError("Backup genom symlink är inte tillåten.")
        base = base.resolve(strict=False)
        candidate = current.resolve(strict=False)

        try:
            candidate.relative_to(
                base
            )
        except ValueError as error:
            raise PermissionError(
                "Rollback-backup försökte lämna backup-roten."
            ) from error

        return candidate

    def _verified_backup(self, rollback_root, relative, expected_hash):
        """Do not follow backup symlinks or accept multiply-linked backups."""
        backup = self._safe_backup_path(rollback_root, relative)
        try:
            observed = _hash_existing_regular_path(backup)
        except (OSError, PermissionError, RuntimeError) as error:
            raise RuntimeError(
                "Osäker backupfil (symlink eller hårdlänk)."
            ) from error
        if observed != expected_hash:
            raise RuntimeError("Backup är skadad eller saknas.")
        return backup

    @contextmanager
    def _backup_verified_snapshot(self, rollback_root, relative, expected_hash):
        """Snapshot a verified backup via one pinned backup-directory inode.

        The yielded Path is still reopened by the restoration caller, which
        must itself reject symlinks; no external path is read or modified if
        the original directory alias is later moved.
        """
        backup = self._verified_backup(rollback_root, relative, expected_hash)
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        with _pinned_parent(backup) as (parent_fd, name):
            try:
                descriptor = os.open(name, flags, dir_fd=parent_fd)
            except OSError as error:
                raise RuntimeError("Backup kan inte öppnas säkert.") from error

            temporary = (
                ".verified-backup-" + secrets.token_hex(12) + ".tmp"
            )
            snapshot = backup.parent / temporary
            created = False
            try:
                with os.fdopen(descriptor, "rb") as source:
                    info = os.fstat(source.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise RuntimeError("Osäker backupfil vid återställning.")

                    create_flags = (
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                        | getattr(os, "O_CLOEXEC", 0)
                    )
                    out_fd = os.open(
                        temporary, create_flags, 0o600, dir_fd=parent_fd
                    )
                    created = True
                    with os.fdopen(out_fd, "wb") as destination:
                        digest = hashlib.sha256()
                        copied = 0
                        while True:
                            part = source.read(1024 * 1024)
                            if not part:
                                break
                            copied += len(part)
                            digest.update(part)
                            destination.write(part)
                        if digest.hexdigest() != expected_hash:
                            raise RuntimeError(
                                "Backup ändrades efter verifiering; återställning stoppas."
                            )
                        after = os.fstat(source.fileno())
                        if (
                            copied != info.st_size
                            or after.st_dev != info.st_dev
                            or after.st_ino != info.st_ino
                            or after.st_size != info.st_size
                            or after.st_mtime_ns != info.st_mtime_ns
                            or after.st_ctime_ns != info.st_ctime_ns
                        ):
                            raise RuntimeError(
                                "Backup ändrades efter verifiering; återställning stoppas."
                            )
                        # Preserve ordinary owner/group/other mode bits only.
                        os.fchmod(
                            destination.fileno(),
                            stat.S_IMODE(info.st_mode) & 0o777,
                        )
                        destination.flush()
                        os.fsync(destination.fileno())
                os.fsync(parent_fd)
                yield snapshot
            finally:
                if created:
                    try:
                        os.unlink(temporary, dir_fd=parent_fd)
                    except FileNotFoundError:
                        pass
                    os.fsync(parent_fd)

    @staticmethod
    def _unlink_verified_added(target, expected_hash):
        """Remove an added file only if its pinned regular inode still matches.

        The parent lookup and unlink use one open dirfd. This prevents a
        parent-symlink swap from redirecting deletion outside the project.
        Python/POSIX unlink is not an atomic hash-and-unlink CAS; the
        cooperating writer lock and OS permissions remain necessary.
        """
        if not isinstance(expected_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_hash
        ):
            raise RuntimeError("Rollback saknar giltig hash för ny fil.")
        from core.selfdev_workspace import _hash_pinned_regular_file

        with _pinned_parent(target) as (directory_fd, name):
            flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            try:
                descriptor = os.open(name, flags, dir_fd=directory_fd)
            except OSError as error:
                raise RuntimeError(
                    "Ny fil saknas eller har ändrats under rollback."
                ) from error
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise RuntimeError("Rollback vägrar ta bort osäker ny fil.")
                if _hash_pinned_regular_file(descriptor) != expected_hash:
                    raise RuntimeError(
                        "Ny fil har ändrats; rollback vägrar radera."
                    )
                # Reject alias exchanges that happened while hashing.
                now = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if (
                    not stat.S_ISREG(now.st_mode)
                    or now.st_nlink != 1
                    or now.st_dev != before.st_dev
                    or now.st_ino != before.st_ino
                    or now.st_size != before.st_size
                    or now.st_mtime_ns != before.st_mtime_ns
                    or now.st_ctime_ns != before.st_ctime_ns
                ):
                    raise RuntimeError(
                        "Ny fil ändrades före rollback-borttagning."
                    )
                os.unlink(name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            finally:
                os.close(descriptor)

    def _restore_from_backup(
        self,
        rollback_root,
        backups,
        paths,
        *,
        expected_after=None,
    ):
        for relative in reversed(list(paths)):
            info = backups[relative]
            target = self._safe_project_target(relative)
            if info["existed"]:
                with self._backup_verified_snapshot(
                    rollback_root, relative, info["sha256"]
                ) as backup:
                    _atomic_copy(backup, target)
            else:
                # Every added-file deletion must be backed by the content
                # digest from the signed journal or verified staging manifest.
                expected = (
                    expected_after.get(relative)
                    if isinstance(expected_after, dict)
                    else None
                )
                self._unlink_verified_added(target, expected)

    def inspect_recovery_artifacts(self, promotion_id):
        """Report orphaned restore snapshots without reading or deleting them.

        Files left by SIGKILL/power loss are *not* automatically removed;
        human review must determine whether recovery is still pending.
        """
        identifier = _safe_identifier(promotion_id)
        rollback_root = (
            self.workspace.session_root / "rollbacks" / identifier
        )
        result = {
            "promotion_id": identifier,
            "read_only": True,
            "status": "blocked",
            "orphan_snapshot_count": 0,
        }
        try:
            # Inspect links without resolving them or traversing outside.
            for directory in (
                self.workspace.session_root,
                self.workspace.session_root / "rollbacks",
                rollback_root,
                rollback_root / "files",
            ):
                if directory.is_symlink():
                    raise PermissionError("Återställningskatalogen är en symlink.")
            backup_root = rollback_root / "files"
            if not backup_root.exists():
                result["status"] = "no_artifacts"
                return result
            if not backup_root.is_dir():
                raise RuntimeError("Backup-roten är inte en katalog.")

            stack = [backup_root]
            inspected = 0
            count = 0
            while stack:
                directory = stack.pop()
                if directory.is_symlink():
                    raise PermissionError("Symlink i återställningskatalogen.")
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        inspected += 1
                        if inspected > 5000:
                            raise RuntimeError(
                                "För många filer i återställningskatalogen."
                            )
                        if entry.is_symlink():
                            raise PermissionError(
                                "Symlink i återställningskatalogen."
                            )
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            continue
                        if entry.name.startswith(".verified-backup-") and (
                            entry.name.endswith(".tmp")
                        ):
                            info = entry.stat(follow_symlinks=False)
                            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                                raise RuntimeError(
                                    "Osäker temporär återställningsfil."
                                )
                            count += 1
            result["orphan_snapshot_count"] = count
            result["status"] = (
                "orphan_snapshots_detected" if count else "no_artifacts"
            )
        except (OSError, RuntimeError, ValueError) as error:
            result["status"] = "blocked"
            result["reason"] = str(error)
        return result

    def inspect_recovery(self, promotion_id):
        """Read-only advisory preflight; NEVER writes audit, locks or source.

        Reports consistency at the instant of inspection, not authorization
        to bypass explicit recovery approval or concurrent-writer protection.
        """
        identifier = _safe_identifier(promotion_id)
        path = (
            self.workspace.session_root / "rollbacks"
            / identifier / "promotion.json"
        )
        result = {
            "promotion_id": identifier,
            "status": "blocked",
            "journal_state": None,
            "file_count": 0,
            "would_restore": 0,
            "read_only": True,
        }
        try:
            record = self._read_journal(path)
            if (
                not isinstance(record, dict)
                or record.get("promotion_id") != identifier
                or record.get("session_id") != self.workspace.session_id
            ):
                raise RuntimeError("Journalen gäller fel session.")
            state = record.get("state")
            result["journal_state"] = state
            if state in {"completed", "recovered", "reverted"}:
                result["status"] = "completed_or_resolved"
                return result
            if state not in {"prepared", "rollback_prepared"}:
                raise RuntimeError("Journalen har okänt eller osäkert tillstånd.")
            backups = record.get("backups")
            planned = record.get("planned_hashes")
            if (
                not isinstance(backups, dict)
                or not isinstance(planned, dict)
                or not backups
                or set(backups) != set(planned)
            ):
                raise RuntimeError("Journalen har ofullständiga filuppgifter.")
            needed = 0
            for relative, item in backups.items():
                if not isinstance(relative, str) or not isinstance(item, dict):
                    raise RuntimeError("Journalen har ogiltiga filuppgifter.")
                expected = planned[relative]
                if (
                    not isinstance(expected, str)
                    or len(expected) != 64
                    or any(ch not in "0123456789abcdef" for ch in expected)
                ):
                    raise RuntimeError("Ogiltig planerad filhash.")
                target = self._safe_project_target(relative)
                existed = item.get("existed")
                if type(existed) is not bool:
                    raise RuntimeError("Ogiltiga uppgifter om ursprungsfil.")
                original = item.get("sha256")
                if existed:
                    if (
                        not isinstance(original, str)
                        or len(original) != 64
                        or any(ch not in "0123456789abcdef" for ch in original)
                    ):
                        raise RuntimeError("Ogiltig ursprungshash.")
                    self._verified_backup(
                        self.workspace.session_root / "rollbacks" / identifier,
                        relative,
                        original,
                    )
                    if not target.is_file():
                        raise RuntimeError("Ursprungsfil saknas eller har ändrats.")
                    current = _sha256(target)
                    if current not in {original, expected}:
                        raise RuntimeError("Extern kodändring blockerar återställning.")
                    if current != original:
                        needed += 1
                else:
                    if original is not None:
                        raise RuntimeError("Felaktigt original för ny fil.")
                    if os.path.lexists(target):
                        if not target.is_file() or _sha256(target) != expected:
                            raise RuntimeError("Extern kodändring blockerar återställning.")
                        needed += 1
            result["file_count"] = len(backups)
            result["would_restore"] = needed
            result["status"] = "preflight_ok_requires_manual_approval"
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            result["status"] = "blocked"
            result["reason"] = str(error)
        return result

    def recover_interrupted(self, promotion_id, approval_phrase):
        """Explicit, idempotent recovery; never triggered automatically."""
        identifier = _safe_identifier(promotion_id)
        expected = (
            "RECOVER " + self.workspace.session_id + " " + identifier
        )
        target_label = "selfdev/" + self.workspace.session_id
        self.audit_logger.write_attempt(
            action="selfdev_recover",
            component="selfdev",
            target=target_label,
            details={"promotion_id": identifier},
        )
        try:
            if str(approval_phrase) != expected:
                raise PermissionError("Fel manuell recovery-frase.")
            with self._project_mutation_lock():
                record = self._recover_interrupted_impl(identifier)
        except Exception as error:
            self.audit_logger.write_result(
                action="selfdev_recover",
                component="selfdev",
                outcome=audit_outcome_for_exception(error),
                target=target_label,
                details={
                    "promotion_id": identifier,
                    "error_type": type(error).__name__,
                },
            )
            raise
        self.audit_logger.write_result(
            action="selfdev_recover",
            component="selfdev",
            outcome="success",
            target=target_label,
            details={"promotion_id": identifier},
        )
        return record

    def _recover_interrupted_impl(self, identifier):
        rollback_root = self.workspace.session_root / "rollbacks" / identifier
        record_path = rollback_root / "promotion.json"
        record = self._read_journal(record_path)
        if (
            not isinstance(record, dict)
            or record.get("state") not in {"prepared", "rollback_prepared"}
        ):
            raise RuntimeError(
                "Återställning kräver en ofullständig prepared-journal."
            )
        if (
            record.get("promotion_id") != identifier
            or record.get("session_id") != self.workspace.session_id
        ):
            raise PermissionError("Återställningsjournalen gäller fel session.")

        backups = record.get("backups")
        planned = record.get("planned_hashes")
        if (
            not isinstance(backups, dict)
            or not isinstance(planned, dict)
            or not backups
            or set(backups) != set(planned)
        ):
            raise RuntimeError("Ofullständiga återställningsuppgifter.")

        # Complete validation before the first write, so a later, unrelated
        # change to one file cannot cause a partially restored project.
        need_restore = []
        for relative, before in backups.items():
            if not isinstance(relative, str) or not isinstance(before, dict):
                raise RuntimeError("Ogiltiga återställningsuppgifter.")
            if (
                not relative
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
            ):
                raise PermissionError("Otillåten återställningssökväg.")
            target = self._safe_project_target(relative)
            after_sha = planned[relative]
            if not isinstance(after_sha, str) or len(after_sha) != 64:
                raise RuntimeError("Ogiltigt SHA256 i journalen.")
            existed = before.get("existed")
            if type(existed) is not bool:
                raise RuntimeError("Ogiltigt backupstatus i journalen.")
            expected_original = before.get("sha256")
            if existed:
                self._verified_backup(
                    rollback_root, relative, expected_original
                )
                if not target.is_file():
                    raise RuntimeError(
                        "Aktiv fil saknas eller har ändrats efter avbrottet."
                    )
                current_sha = _sha256(target)
                if current_sha not in {expected_original, after_sha}:
                    raise RuntimeError(
                        "Aktiv källkod har nyare arbete; återställning stoppades."
                    )
                if current_sha != expected_original:
                    need_restore.append(relative)
            else:
                if expected_original is not None:
                    raise RuntimeError("Ogiltig backupmetadata.")
                if target.exists():
                    if not target.is_file() or _sha256(target) != after_sha:
                        raise RuntimeError(
                            "Aktiv källkod har nyare arbete; återställning stoppades."
                        )
                    need_restore.append(relative)

        self._restore_from_backup(
            rollback_root, backups, need_restore,
            expected_after=planned,
        )
        record["state"] = "recovered"
        record["rolled_back"] = True
        record["recovered_unix_time"] = time.time()
        self._write_journal(record_path, record)
        return record

    def migrate_legacy_completed(self, promotion_id, approval_phrase):
        """Explicit metadata-only migration of a VERIFIED completed legacy journal.

        Unsigned interrupted journals are deliberately not recoverable here.
        This provides consistency checking, not cryptographic provenance
        of historic unsigned files.
        """
        identifier = _safe_identifier(promotion_id)
        expected = (
            "MIGRATE LEGACY " + self.workspace.session_id + " " + identifier
        )
        label = "selfdev/" + self.workspace.session_id
        self.audit_logger.write_attempt(
            action="selfdev_migrate_legacy",
            component="selfdev",
            target=label,
            details={"promotion_id": identifier},
        )
        try:
            if str(approval_phrase) != expected:
                raise PermissionError("Fel manuell migreringsfras.")
            with self._project_mutation_lock():
                self._require_promotion_enabled()
                result = self._migrate_legacy_completed_impl(identifier)
        except Exception as error:
            self.audit_logger.write_result(
                action="selfdev_migrate_legacy",
                component="selfdev",
                outcome=audit_outcome_for_exception(error),
                target=label,
                details={
                    "promotion_id": identifier,
                    "error_type": type(error).__name__,
                },
            )
            raise
        self.audit_logger.write_result(
            action="selfdev_migrate_legacy",
            component="selfdev",
            outcome="success",
            target=label,
            details={"promotion_id": identifier},
        )
        return result

    def _migrate_legacy_completed_impl(self, identifier):
        root = self.workspace.session_root / "rollbacks" / identifier
        if root.is_symlink():
            raise PermissionError("Migrering genom symlink är inte tillåten.")
        source = root / "promotion.json"
        if source.is_symlink():
            raise PermissionError("Migrering av journal-symlink nekad.")
        if not source.is_file():
            raise FileNotFoundError("Legacy-journal saknas.")
        # Strict read also prevents duplicate JSON keys from selecting an
        # unexpected session, state or backup file during legacy migration.
        record, raw = self._read_recovery_json(source, include_raw=True)
        if not isinstance(record, dict):
            raise RuntimeError("Legacy-journalen är ogiltig.")
        if "journal_hmac" in record or "journal_version" in record:
            raise RuntimeError("Journalen är inte en osignerad legacy-journal.")
        if (
            record.get("session_id") != self.workspace.session_id
            or record.get("promotion_id") != identifier
        ):
            raise PermissionError("Legacy-journalen gäller annan session.")
        if (
            record.get("state") not in (None, "completed")
            or record.get("rolled_back") is not False
            or not isinstance(record.get("promoted_unix_time"), (int, float))
            or isinstance(record.get("promoted_unix_time"), bool)
            or record["promoted_unix_time"] <= 0
        ):
            raise RuntimeError(
                "Endast slutförda legacy-journaler får migreras."
            )
        backups = record.get("backups")
        after = record.get("after_hashes")
        changed = record.get("changed")
        added = record.get("added")
        if (
            not isinstance(backups, dict)
            or not isinstance(after, dict)
            or not isinstance(changed, list)
            or not isinstance(added, list)
            or not backups
            or not all(isinstance(p, str) for p in changed + added)
            or len(set(changed + added)) != len(changed + added)
            or set(backups) != set(after)
            or set(backups) != set(changed + added)
        ):
            raise RuntimeError("Ofullständiga legacy-journaluppgifter.")
        def is_sha(value):
            return (
                isinstance(value, str) and len(value) == 64
                and all(char in "0123456789abcdef" for char in value)
            )
        for relative, expected_after in after.items():
            if not isinstance(relative, str) or not is_sha(expected_after):
                raise RuntimeError("Ogiltiga legacy-journalhashar.")
            target = self._safe_project_target(relative)
            if not target.is_file() or _sha256(target) != expected_after:
                raise RuntimeError(
                    "Aktiv kod skiljer sig från legacy-journalen."
                )
            item = backups[relative]
            if not isinstance(item, dict) or type(item.get("existed")) is not bool:
                raise RuntimeError("Ogiltig legacy-backupmetadata.")
            if relative in changed:
                if not item["existed"] or not is_sha(item.get("sha256")):
                    raise RuntimeError("Legacy-backup är ogiltig.")
                self._verified_backup(root, relative, item["sha256"])
            else:
                if item["existed"] or item.get("sha256") is not None:
                    raise RuntimeError("Legacy-added har felaktig backup.")

        archive = root / "promotion.legacy-unsigned.json"
        if archive.is_symlink():
            raise PermissionError("Legacy-arkivet är en symlink.")
        if os.path.lexists(archive):
            attributes = archive.lstat()
            if (
                not stat.S_ISREG(attributes.st_mode)
                or attributes.st_nlink != 1
                or (os.name == "posix" and attributes.st_mode & 0o077)
                or archive.read_bytes() != raw
            ):
                raise RuntimeError("Legacy-arkivet matchar inte originaljournalen.")
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(str(archive), flags, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            _sync_directory(root)
        self._write_journal(source, record)
        return self._read_journal(source)

    def rollback(
        self,
        promotion_id,
        approval_phrase,
    ):
        target = (
            "selfdev/"
            + self.workspace.session_id
        )
        self.audit_logger.write_attempt(
            action="selfdev_rollback",
            component="selfdev",
            target=target,
            details={
                "session_id": (
                    self.workspace.session_id
                ),
                "promotion_id": str(
                    promotion_id
                ),
            },
        )

        try:
            with self._project_mutation_lock():
                record = self._rollback_impl(
                    promotion_id,
                    approval_phrase,
                )
        except Exception as error:
            self.audit_logger.write_result(
                action="selfdev_rollback",
                component="selfdev",
                outcome=(
                    audit_outcome_for_exception(
                        error
                    )
                ),
                target=target,
                details={
                    "session_id": (
                        self.workspace.session_id
                    ),
                    "promotion_id": str(
                        promotion_id
                    ),
                    "error_type": type(
                        error
                    ).__name__,
                },
            )
            raise

        self.audit_logger.write_result(
            action="selfdev_rollback",
            component="selfdev",
            outcome="success",
            target=target,
            details={
                "session_id": (
                    self.workspace.session_id
                ),
                "promotion_id": record.get(
                    "promotion_id"
                ),
            },
        )
        return record

    def _rollback_impl(
        self,
        promotion_id,
        approval_phrase,
    ):
        identifier = _safe_identifier(
            promotion_id
        )
        expected = (
            "ROLLBACK "
            + self.workspace.session_id
            + " "
            + identifier
        )

        if str(
            approval_phrase
        ) != expected:
            raise PermissionError(
                "Fel manuell rollback-frase."
            )

        rollback_root = (
            self.workspace
            .session_root
            / "rollbacks"
            / identifier
        )
        record_path = (
            rollback_root
            / "promotion.json"
        )

        if not record_path.exists():
            raise FileNotFoundError(
                "Promotion-record saknas."
            )

        record = self._read_journal(record_path)
        if not isinstance(record, dict):
            raise RuntimeError("Ogiltig återställningsjournal.")
        state = record.get("state")
        if state == "prepared":
            raise RuntimeError(
                "Ofullständig promotion kräver RECOVER, inte vanlig ROLLBACK."
            )
        if state in {"reverted", "recovered"}:
            raise RuntimeError("Promotionen är redan återställd.")
        if state not in {"completed", None}:
            raise RuntimeError("Okänt promotion-läge; rollback avböjs.")
        if state is None and not record.get("promoted_unix_time"):
            raise RuntimeError("Äldre rollback-record saknar slutförd promotion.")

        if record.get(
            "rolled_back",
            False,
        ):
            raise RuntimeError(
                "Promotionen är redan rollbackad."
            )

        after_hashes = record.get(
            "after_hashes",
            {},
        )

        for relative, expected_hash in (
            after_hashes.items()
        ):
            target = (
                self._safe_project_target(
                    relative
                )
            )

            if (
                not target.exists()
                or _sha256(
                    target
                )
                != expected_hash
            ):
                raise RuntimeError(
                    "Aktiv källkod har ändrats efter promotion; "
                    "automatisk rollback vägrar skriva över nyare arbete: "
                    + relative
                )

        backups = record.get("backups", {})
        if not isinstance(backups, dict) or set(backups) != set(after_hashes):
            raise RuntimeError("Ofullständig rollback-metadata.")
        paths = sorted(backups)
        for relative, information in backups.items():
            if not isinstance(information, dict):
                raise RuntimeError("Ogiltig rollback-backup.")
            if information.get("existed"):
                self._verified_backup(
                    rollback_root, relative, information.get("sha256")
                )
        # A crash in the middle of a normal rollback otherwise leaves
        # mixed old/new files and a misleading "completed" journal.
        record["state"] = "rollback_prepared"
        self._write_journal(record_path, record)
        self._restore_from_backup(
            rollback_root,
            backups,
            paths,
            expected_after=after_hashes,
        )

        record[
            "rolled_back"
        ] = True
        record["state"] = "recovered"
        record[
            "rolled_back_unix_time"
        ] = time.time()
        self._write_journal(record_path, record)

        return record
