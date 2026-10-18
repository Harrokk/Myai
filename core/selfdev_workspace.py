import hmac
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
from contextlib import contextmanager


_ALLOWED_DIRS = {
    "core",
    "modules",
    "tests",
    "scripts",
    "config",
    "docs",
    "firmware",
}
_ALLOWED_ROOT_FILES = {
    "mail.py",
    "MyAI_PROJECT_SPEC.md",
}
_ALLOWED_SUFFIXES = {
    ".py",
    ".json",
    ".md",
    ".txt",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
}
_SESSION_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{1,64}$"
)


def _sha256(path):
    digest = hashlib.sha256()

    with Path(path).open(
        "rb"
    ) as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def _safe_session_id(value=None):
    session_id = (
        str(value)
        if value is not None
        else secrets.token_hex(8)
    )

    if not _SESSION_PATTERN.fullmatch(
        session_id
    ):
        raise ValueError(
            "Ogiltigt selfdev-session-ID."
        )

    return session_id


def _is_allowed_root_file(path):
    name = path.name

    return (
        name in _ALLOWED_ROOT_FILES
        or (
            name.startswith(
                "requirements"
            )
            and path.suffix
            == ".txt"
        )
    )


def _allowed_relative_path(
    relative_path,
):
    path = Path(
        relative_path
    )

    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
    ):
        return False

    if any(
        part in {
            ".git",
            "runtime",
            "__pycache__",
            ".venv",
            "venv",
        }
        for part in path.parts
    ):
        return False

    if len(path.parts) == 1:
        return (
            _is_allowed_root_file(
                path
            )
            and path.suffix
            in _ALLOWED_SUFFIXES
        )

    return (
        path.parts[0]
        in _ALLOWED_DIRS
        and path.suffix
        in _ALLOWED_SUFFIXES
    )


def _stage_source_files(project_root, workspace_root, *, target_dir_fd=None):
    """Stage approved sources and hash the very bytes copied from pinned FDs.

    The project root is operator-trusted. Each descendant and final file is
    opened with O_NOFOLLOW, avoiding symlink swaps after enumeration.
    """
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise RuntimeError("Säker källkopiering kräver Linux dir_fd.")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    file_flags |= getattr(os, "O_CLOEXEC", 0)
    create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    create_flags |= getattr(os, "O_CLOEXEC", 0)
    baseline = {}

    def visit(source_fd, target_fd, parts=()):
        # Enumeration is relative to the already open directory, but every
        # entry is checked and opened again relative to that SAME inode.
        with os.scandir(source_fd) as entries:
            names = sorted(entry.name for entry in entries)

        for name in names:
            if name in {"", ".", ".."}:
                continue
            relative_parts = (*parts, name)
            relative = Path(*relative_parts)
            try:
                details = os.stat(
                    name, dir_fd=source_fd, follow_symlinks=False
                )
            except FileNotFoundError as error:
                raise RuntimeError(
                    "En källfil försvann under selfdev-kopieringen."
                ) from error

            if stat.S_ISLNK(details.st_mode):
                continue

            if stat.S_ISDIR(details.st_mode):
                if len(relative_parts) == 1:
                    permitted_dir = name in _ALLOWED_DIRS
                else:
                    permitted_dir = _allowed_relative_path(
                        Path(*parts, "placeholder.py")
                    )
                if not permitted_dir or name in {
                    ".git", "runtime", "__pycache__", ".venv", "venv"
                }:
                    continue

                source_child = os.open(
                    name, directory_flags, dir_fd=source_fd
                )
                try:
                    _require_enumerated_inode(details, source_child)
                    # The session workspace is newly created, so an
                    # unexpected existing destination is not trusted.
                    os.mkdir(name, mode=0o700, dir_fd=target_fd)
                    target_child = os.open(
                        name, directory_flags, dir_fd=target_fd
                    )
                    try:
                        visit(source_child, target_child, relative_parts)
                    finally:
                        os.close(target_child)
                finally:
                    os.close(source_child)
                continue

            if not stat.S_ISREG(details.st_mode):
                continue
            if not _allowed_relative_path(relative):
                continue

            source_file = os.open(name, file_flags, dir_fd=source_fd)
            try:
                before = _require_enumerated_inode(details, source_file)
                if not stat.S_ISREG(before.st_mode):
                    raise PermissionError(
                        "Källfilen ändrades till en specialfil."
                    )
                if before.st_nlink != 1:
                    raise PermissionError(
                        "Selfdev-källfilen har otillåtna hårdlänkar."
                    )
                target_file = os.open(
                    name, create_flags, 0o600, dir_fd=target_fd
                )
                try:
                    digest = hashlib.sha256()
                    copied = 0
                    while True:
                        chunk = os.read(source_file, 65_536)
                        if not chunk:
                            break
                        copied += len(chunk)
                        digest.update(chunk)
                        view = memoryview(chunk)
                        while view:
                            written = os.write(target_file, view)
                            if written <= 0:
                                raise OSError("Kunde inte skriva staging-filen.")
                            view = view[written:]

                    after = os.fstat(source_file)
                    if (
                        copied != before.st_size
                        or before.st_dev != after.st_dev
                        or before.st_ino != after.st_ino
                        or before.st_size != after.st_size
                        or before.st_mtime_ns != after.st_mtime_ns
                        or before.st_ctime_ns != after.st_ctime_ns
                        or after.st_nlink != 1
                    ):
                        raise RuntimeError(
                            "Källfilen ändrades under selfdev-kopieringen."
                        )
                    # Keep executable-bit semantics from copy2 without
                    # propagating setuid/setgid/sticky or extended attributes.
                    os.fchmod(target_file, stat.S_IMODE(before.st_mode) & 0o777)
                    os.fsync(target_file)
                    baseline[relative.as_posix()] = digest.hexdigest()
                finally:
                    os.close(target_file)
            finally:
                os.close(source_file)

    source_fd = _open_directory_nofollow(project_root)
    try:
        target_fd = (
            os.dup(target_dir_fd)
            if target_dir_fd is not None
            else _open_directory_nofollow(workspace_root)
        )
        try:
            visit(source_fd, target_fd)
        finally:
            os.close(target_fd)
    finally:
        os.close(source_fd)
    return baseline


def _manifest_open_flags():
    """Required POSIX no-follow flags for integrity reads."""
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise RuntimeError("Säker selfdev-integritetskontroll kräver Linux dir_fd.")
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | close_on_exec
    file_flags = (
        os.O_RDONLY | os.O_NOFOLLOW
        | getattr(os, "O_NONBLOCK", 0) | close_on_exec
    )
    return directory_flags, file_flags


def _open_directory_nofollow(root):
    """Open an absolute directory without following ANY parent symlink.

    O_NOFOLLOW on a full pathname protects only the final component.
    Traverse from / using directory-relative O_DIRECTORY|O_NOFOLLOW opens
    and return the pinned directory descriptor, closing on any failure.
    """
    root = Path(root)
    if not root.is_absolute() or ".." in root.parts:
        raise PermissionError("Selfdev-katalogen måste ha en säker absolut sökväg.")
    directory_flags, _ = _manifest_open_flags()
    directory_fd = os.open("/", directory_flags)
    try:
        for part in root.parts[1:]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except BaseException:
        os.close(directory_fd)
        raise


def _require_enumerated_inode(listed, opened_fd):
    """Require the inode opened by dirfd to be the inode enumerated earlier.

    No-follow prevents symlinks, but cannot detect replacement by a distinct
    regular file or directory with the same basename between stat and open.
    """
    observed = os.fstat(opened_fd)
    if (
        listed.st_dev != observed.st_dev
        or listed.st_ino != observed.st_ino
        or stat.S_IFMT(listed.st_mode) != stat.S_IFMT(observed.st_mode)
    ):
        raise PermissionError(
            "Selfdev-filen eller katalogen byttes mellan kontroll och öppning."
        )
    return observed


def _hash_pinned_regular_file(file_fd):
    """Hash only the already opened regular inode, rejecting detectable edits."""
    before = os.fstat(file_fd)
    if not stat.S_ISREG(before.st_mode):
        raise PermissionError("Selfdev-kontroll kräver en vanlig källfil.")
    if before.st_nlink != 1:
        raise PermissionError(
            "Selfdev-kontroll avvisar källfil med hårdlänkar."
        )

    digest = hashlib.sha256()
    counted = 0
    while True:
        block = os.read(file_fd, 65_536)
        if not block:
            break
        counted += len(block)
        digest.update(block)

    after = os.fstat(file_fd)
    if (
        counted != before.st_size
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or after.st_nlink != 1
    ):
        raise RuntimeError("Selfdev-källfilen ändrades under hashkontrollen.")
    return digest.hexdigest()


def _manifest_parts(relative):
    """Reject forged session metadata paths before any open or traversal."""
    if not isinstance(relative, str):
        raise PermissionError("Ogiltig selfdev-sökväg i sessionsmetadata.")
    parts = relative.split("/")
    if (
        any(part in {"", ".", ".."} or chr(0) in part for part in parts)
        or not _allowed_relative_path(Path(relative))
        or Path(*parts).as_posix() != relative
    ):
        raise PermissionError("Otillåten selfdev-sökväg i sessionsmetadata.")
    return parts


def _hash_allowed_relative(root, relative):
    """Read one allowlisted session-baseline path via pinned directory FDs."""
    parts = _manifest_parts(relative)
    directory_flags, file_flags = _manifest_open_flags()
    directory_fd = _open_directory_nofollow(root)
    try:
        for component in parts[:-1]:
            child_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
        file_fd = os.open(parts[-1], file_flags, dir_fd=directory_fd)
        try:
            return _hash_pinned_regular_file(file_fd)
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)


def build_manifest(root):
    """Hash only approved regular files through anchored non-follow opens.

    A missing root preserves the old empty-manifest behavior. An existing
    untrusted symlink/root or swapped descendant must fail closed.
    """
    root = Path(root)
    directory_flags, file_flags = _manifest_open_flags()
    result = {}

    def visit(directory_fd, parts=()):
        with os.scandir(directory_fd) as scan:
            names = sorted(entry.name for entry in scan)

        for name in names:
            if name in {"", ".", ".."}:
                continue

            relative_parts = (*parts, name)
            relative = Path(*relative_parts)
            metadata = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False
            )
            if stat.S_ISLNK(metadata.st_mode):
                continue

            if stat.S_ISDIR(metadata.st_mode):
                if name in {
                    ".git", "runtime", "__pycache__", ".venv", "venv"
                }:
                    continue
                if not parts:
                    if name not in _ALLOWED_DIRS:
                        continue
                elif not _allowed_relative_path(Path(*relative_parts, "probe.py")):
                    continue

                child_fd = os.open(name, directory_flags, dir_fd=directory_fd)
                try:
                    _require_enumerated_inode(metadata, child_fd)
                    visit(child_fd, relative_parts)
                finally:
                    os.close(child_fd)
                continue

            if not stat.S_ISREG(metadata.st_mode):
                continue
            if not _allowed_relative_path(relative):
                continue

            file_fd = os.open(name, file_flags, dir_fd=directory_fd)
            try:
                _require_enumerated_inode(metadata, file_fd)
                result[relative.as_posix()] = _hash_pinned_regular_file(file_fd)
            finally:
                os.close(file_fd)

    try:
        root_fd = _open_directory_nofollow(root)
    except FileNotFoundError:
        # Preserve the empty manifest for a missing optional root.
        return {}
    try:
        visit(root_fd)
    finally:
        os.close(root_fd)
    return result

def manifest_digest(
    manifest,
):
    payload = json.dumps(
        dict(
            sorted(
                manifest.items()
            )
        ),
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        payload
    ).hexdigest()


@contextmanager
def _new_private_session_workspace(session_root):
    """Create a new session and workspace through pinned no-follow dirs.

    The yielded workspace FD remains pinned while approved project sources
    are staged. Never reuse an existing session or follow its symlink.
    """
    session_root = Path(session_root)
    if not session_root.is_absolute() or ".." in session_root.parts:
        raise PermissionError("Sessionsroten måste vara en absolut säker sökväg.")
    if not all(hasattr(os, key) for key in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise RuntimeError("Säkert skapande av session kräver Linux dir_fd.")
    flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    directory_fd = os.open("/", flags)
    try:
        for part in session_root.parts[1:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=directory_fd)
            except FileExistsError:
                pass
            next_fd = os.open(part, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd

        parent = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or parent.st_mode & 0o022
        ):
            raise PermissionError("Selfdev-sessionens förälder är osäker.")
        # O_EXCL-like directory creation: even a dangling symlink or
        # previously existing directory is rejected by mkdir.
        os.mkdir(session_root.name, mode=0o700, dir_fd=directory_fd)
        session_fd = os.open(session_root.name, flags, dir_fd=directory_fd)
        try:
            session_info = os.fstat(session_fd)
            if (
                session_info.st_uid != os.geteuid()
                or session_info.st_mode & 0o077
            ):
                raise PermissionError("Selfdev-sessionen är inte privat.")
            os.mkdir("workspace", mode=0o700, dir_fd=session_fd)
            workspace_fd = os.open("workspace", flags, dir_fd=session_fd)
            try:
                workspace_info = os.fstat(workspace_fd)
                if (
                    workspace_info.st_uid != os.geteuid()
                    or workspace_info.st_mode & 0o077
                ):
                    raise PermissionError("Staging-workspacen är inte privat.")
                os.fsync(workspace_fd)
                os.fsync(session_fd)
                os.fsync(directory_fd)
                yield workspace_fd
            finally:
                os.close(workspace_fd)
        finally:
            os.close(session_fd)
    finally:
        os.close(directory_fd)


class SelfDevWorkspace:
    def __init__(
        self,
        project_root,
        session_id,
        *,
        selfdev_root=None,
    ):
        self.project_root = Path(
            project_root
        ).resolve()
        self.session_id = (
            _safe_session_id(
                session_id
            )
        )
        base = (
            Path(
                selfdev_root
            )
            if selfdev_root
            is not None
            else (
                self.project_root
                / "runtime"
                / "selfdev"
            )
        )
        # Retain the lexical directory spelling. Resolving here would
        # silently follow a preexisting selfdev-root symlink before creation
        # can reject it with O_NOFOLLOW.
        self.session_root = (
            base.absolute()
            / self.session_id
        )
        self.workspace_root = (
            self.session_root
            / "workspace"
        )
        self.metadata_path = (
            self.session_root
            / "session.json"
        )
        self.verification_path = (
            self.session_root
            / "verification.json"
        )

    @classmethod
    def create(
        cls,
        project_root,
        session_id=None,
        *,
        selfdev_root=None,
    ):
        identifier = (
            _safe_session_id(
                session_id
            )
        )
        instance = cls(
            project_root,
            identifier,
            selfdev_root=(
                selfdev_root
            ),
        )

        # Create both directories with relative mkdir under pinned
        # O_DIRECTORY|O_NOFOLLOW parents, then stage into that SAME open
        # workspace inode rather than resolving its mutable pathname again.
        with _new_private_session_workspace(instance.session_root) as target_fd:
            baseline = _stage_source_files(
                instance.project_root,
                instance.workspace_root,
                target_dir_fd=target_fd,
            )

        metadata = {
            "session_id": identifier,
            "created_unix_time": time.time(),
            "project_root": str(
                instance.project_root
            ),
            "baseline": baseline,
            "baseline_digest": (
                manifest_digest(
                    baseline
                )
            ),
        }
        instance.save_session_metadata(metadata)

        return instance

    def _session_directory_fd(self):
        """Require a private owned session inode on every reopen."""
        descriptor = _open_directory_nofollow(self.session_root)
        try:
            details = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(details.st_mode)
                or details.st_uid != os.geteuid()
                or details.st_mode & 0o077
            ):
                raise PermissionError("Osäker selfdev-sessionskatalog.")
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def _read_session_record(self, filename):
        """Read one stable, bounded session JSON inode through pinned dirfds.

        A concurrent writer cannot substitute an outside parent or mix
        multiple revisions of the same regular file without detection.
        """
        directory_fd = self._session_directory_fd()
        try:
            flags = os.O_RDONLY | os.O_NOFOLLOW
            flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
            file_fd = os.open(filename, flags, dir_fd=directory_fd)
            try:
                before = os.fstat(file_fd)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                    or before.st_uid != os.geteuid()
                    or before.st_mode & 0o077
                ):
                    raise PermissionError("Osäker selfdev-sessionsfil.")
                limit = 4 * 1024 * 1024
                if before.st_size > limit:
                    raise ValueError("Selfdev-sessionsfilen är för stor.")

                content = bytearray()
                while len(content) <= limit:
                    block = os.read(
                        file_fd, min(65_536, limit + 1 - len(content))
                    )
                    if not block:
                        break
                    content.extend(block)
                if len(content) > limit:
                    raise ValueError("Selfdev-sessionsfilen är för stor.")

                after = os.fstat(file_fd)
                if (
                    not stat.S_ISREG(after.st_mode)
                    or after.st_nlink != 1
                    or before.st_dev != after.st_dev
                    or before.st_ino != after.st_ino
                    or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                    or before.st_ctime_ns != after.st_ctime_ns
                    or before.st_uid != after.st_uid
                    or stat.S_IMODE(before.st_mode) != stat.S_IMODE(after.st_mode)
                    or len(content) != before.st_size
                ):
                    raise RuntimeError(
                        "Selfdev-sessionsfilen ändrades under läsning."
                    )
            finally:
                os.close(file_fd)
        finally:
            os.close(directory_fd)

        def unique_object_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(
                        "Dubbla fältnamn i selfdev-sessionsfilen."
                    )
                result[key] = value
            return result

        def reject_nonfinite_constant(value):
            raise ValueError(
                "Icke-ändligt numeriskt värde i selfdev-sessionsfilen."
            )

        try:
            record = json.loads(
                bytes(content).decode("utf-8"),
                object_pairs_hook=unique_object_pairs,
                parse_constant=reject_nonfinite_constant,
            )
        except (UnicodeError, RecursionError) as error:
            raise ValueError("Ogiltig JSON i selfdev-sessionsfilen.") from error
        if not isinstance(record, dict):
            raise ValueError("Selfdev-sessionsfilen måste vara ett JSON-objekt.")
        return record

    def _write_session_record(self, filename, data):
        # Publish complete records with an exclusive temp and rename in the
        # same pinned directory. Never follow a pre-existing target symlink.
        directory_fd = self._session_directory_fd()
        temporary = "." + filename + "." + secrets.token_hex(12) + ".tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(
                        data, handle, ensure_ascii=False, indent=2,
                        allow_nan=False,
                    )
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    existing = os.stat(
                        filename, dir_fd=directory_fd, follow_symlinks=False
                    )
                except FileNotFoundError:
                    existing = None
                if existing is not None and (
                    not stat.S_ISREG(existing.st_mode)
                    or existing.st_nlink != 1
                    or existing.st_uid != os.geteuid()
                    or existing.st_mode & 0o077
                ):
                    raise PermissionError("Osäker selfdev-sessionsfil.")
                os.replace(
                    temporary, filename,
                    src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                )
                os.fsync(directory_fd)
            except BaseException:
                try:
                    os.unlink(temporary, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass
                raise
        finally:
            os.close(directory_fd)

    def save_session_metadata(self, record):
        self._write_session_record("session.json", record)

    def metadata(self):
        """Validate the session identity and internal baseline integrity.

        This detects corruption, a record copied from another session or
        project, and partial edits. The unhashed digest is not an
        authentication code against a writer who controls the whole record.
        """
        record = self._read_session_record("session.json")
        if record.get("session_id") != self.session_id:
            raise ValueError("Selfdev-sessionsmetadata gäller fel session.")
        if record.get("project_root") != str(self.project_root):
            raise ValueError("Selfdev-sessionsmetadata gäller fel projektrot.")

        baseline = record.get("baseline")
        if not isinstance(baseline, dict) or len(baseline) > 10_000:
            raise ValueError("Ogiltig selfdev-baseline i sessionsmetadata.")
        for relative, expected in baseline.items():
            _manifest_parts(relative)
            if (
                not isinstance(expected, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            ):
                raise ValueError("Ogiltig SHA-256 i selfdev-baseline.")

        reported_digest = record.get("baseline_digest")
        if (
            not isinstance(reported_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", reported_digest) is None
            or not hmac.compare_digest(
                reported_digest, manifest_digest(baseline)
            )
        ):
            raise ValueError(
                "Selfdev-baslinjens sammandrag stämmer inte."
            )
        return record

    def save_verification(self, record):
        self._write_session_record("verification.json", record)

    def read_verification(self):
        return self._read_session_record("verification.json")

    def invalidate_verification(self):
        directory_fd = self._session_directory_fd()
        try:
            try:
                os.unlink("verification.json", dir_fd=directory_fd)
            except FileNotFoundError:
                return
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _candidate_path(
        self,
        relative_path,
    ):
        relative = Path(
            relative_path
        )

        if not _allowed_relative_path(
            relative
        ):
            raise PermissionError(
                "Selfdev-sökvägen är inte tillåten."
            )

        candidate = (
            self.workspace_root
            / relative
        )
        resolved_parent = (
            candidate.parent.resolve(
                strict=False
            )
        )

        try:
            resolved_parent.relative_to(
                self.workspace_root.resolve()
            )
        except ValueError as error:
            raise PermissionError(
                "Selfdev-sökvägen lämnar staging-workspacen."
            ) from error

        current = (
            self.workspace_root
        )

        for part in relative.parts[:-1]:
            current = (
                current
                / part
            )

            if current.is_symlink():
                raise PermissionError(
                    "Symlänkar är inte tillåtna i selfdev-workspacen."
                )

        if candidate.is_symlink():
            raise PermissionError(
                "Symlänkar är inte tillåtna i selfdev-workspacen."
            )

        return candidate

    def write_text(
        self,
        relative_path,
        content,
    ):
        # Keep lexical allowlisting and existing selfdev preflight checks,
        # but do not rely on these path checks for subsequent file I/O.
        target = self._candidate_path(relative_path)
        relative = Path(relative_path)
        if not all(hasattr(os, key) for key in ("O_DIRECTORY", "O_NOFOLLOW")):
            raise RuntimeError("Säker selfdev-skrivning kräver Linux dir_fd.")

        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        directory_fd = _open_directory_nofollow(self.workspace_root)

        try:
            for component in relative.parts[:-1]:
                # Directories are created and reopened relative to a pinned
                # inode. A concurrent symlink swap must fail at os.open().
                try:
                    os.mkdir(component, mode=0o700, dir_fd=directory_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(component, flags, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd

            filename = relative.name

            def check_target():
                try:
                    details = os.stat(
                        filename,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    return
                if not stat.S_ISREG(details.st_mode):
                    raise PermissionError(
                        "Symlänkar och specialfiler är inte tillåtna "
                        "i selfdev-workspacen."
                    )

            check_target()
            temporary = "." + filename + "." + secrets.token_hex(12) + ".tmp"
            file_flags = (
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0)
            )
            temporary_fd = os.open(
                temporary, file_flags, 0o600, dir_fd=directory_fd
            )
            try:
                with os.fdopen(temporary_fd, "w", encoding="utf-8") as handle:
                    temporary_fd = -1
                    handle.write(str(content))
                    handle.flush()
                    os.fsync(handle.fileno())

                # Recheck an inserted symlink; a last-instant race after
                # this check is safe because rename replaces the entry
                # without following its target.
                check_target()
                os.replace(
                    temporary,
                    filename,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                )
            except BaseException:
                if temporary_fd >= 0:
                    os.close(temporary_fd)
                try:
                    os.unlink(temporary, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass
                raise
        finally:
            os.close(directory_fd)

        self.invalidate_verification()

        return target

    def changed_files(self):
        metadata = self.metadata()
        baseline = metadata.get(
            "baseline",
            {},
        )
        current = build_manifest(
            self.workspace_root
        )
        changed = []
        added = []
        deleted = []

        for path, digest in (
            current.items()
        ):
            previous = baseline.get(
                path
            )

            if previous is None:
                added.append(
                    path
                )
            elif previous != digest:
                changed.append(
                    path
                )

        for path in baseline:
            if path not in current:
                deleted.append(
                    path
                )

        return {
            "changed": sorted(
                changed
            ),
            "added": sorted(
                added
            ),
            "deleted": sorted(
                deleted
            ),
            "manifest": current,
            "manifest_digest": (
                manifest_digest(
                    current
                )
            ),
        }

    def source_drift(
        self,
    ):
        metadata = self.metadata()
        baseline = metadata.get("baseline", {})
        if not isinstance(baseline, dict):
            raise ValueError("Ogiltig selfdev-baseline i sessionsmetadata.")

        drift = []
        for relative, expected in baseline.items():
            # Session metadata may be tampered with. Do not concatenate its
            # strings directly onto a host path and follow arbitrary links.
            _manifest_parts(relative)
            if not isinstance(expected, str) or not re.fullmatch(
                r"[0-9a-f]{64}", expected
            ):
                raise ValueError("Ogiltig SHA-256 i selfdev-baseline.")
            try:
                current = _hash_allowed_relative(self.project_root, relative)
            except OSError:
                # Missing, unreadable and symlink-swapped source entries all
                # count as drift; they cannot silently attest as matching.
                drift.append(relative)
                continue

            if current != expected:
                drift.append(relative)

        return sorted(drift)
