import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time


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


def _stage_source_files(project_root, workspace_root):
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
                before = os.fstat(source_file)
                if not stat.S_ISREG(before.st_mode):
                    raise PermissionError(
                        "Källfilen ändrades till en specialfil."
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

    source_fd = os.open(project_root, directory_flags)
    try:
        target_fd = os.open(workspace_root, directory_flags)
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


def _hash_pinned_regular_file(file_fd):
    """Hash only the already opened regular inode, rejecting detectable edits."""
    before = os.fstat(file_fd)
    if not stat.S_ISREG(before.st_mode):
        raise PermissionError("Selfdev-kontroll kräver en vanlig källfil.")

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
    directory_fd = os.open(root, directory_flags)
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
    if not root.exists() and not root.is_symlink():
        return {}

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
                result[relative.as_posix()] = _hash_pinned_regular_file(file_fd)
            finally:
                os.close(file_fd)

    root_fd = os.open(root, directory_flags)
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
        self.session_root = (
            base.resolve()
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

        if instance.session_root.exists():
            raise FileExistsError(
                "Selfdev-sessionen finns redan."
            )

        instance.workspace_root.mkdir(
            parents=True,
            exist_ok=False,
        )

        # One pinned source descriptor supplies both staged bytes and the
        # baseline digest. No second path-based source hash/read occurs.
        baseline = _stage_source_files(
            instance.project_root,
            instance.workspace_root,
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
        instance.metadata_path.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        return instance

    def metadata(self):
        return json.loads(
            self.metadata_path.read_text(
                encoding="utf-8"
            )
        )

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
        directory_fd = os.open(self.workspace_root, flags)

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

        try:
            self.verification_path.unlink()
        except FileNotFoundError:
            pass

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
        baseline = metadata.get(
            "baseline",
            {},
        )
        drift = []

        for relative, expected in (
            baseline.items()
        ):
            source = (
                self.project_root
                / relative
            )

            if not source.exists():
                drift.append(
                    relative
                )
                continue

            if _sha256(
                source
            ) != expected:
                drift.append(
                    relative
                )

        return sorted(
            drift
        )
