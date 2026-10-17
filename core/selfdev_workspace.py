import hashlib
import json
import os
import tempfile
from pathlib import Path
import re
import secrets
import shutil
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


def _iter_source_files(
    project_root,
):
    root = Path(
        project_root
    )

    for child in sorted(
        root.iterdir(),
        key=lambda item: item.name,
    ):
        if child.is_symlink():
            continue

        if child.is_file():
            if (
                _is_allowed_root_file(
                    child
                )
                and child.suffix
                in _ALLOWED_SUFFIXES
            ):
                yield child
            continue

        if (
            not child.is_dir()
            or child.name
            not in _ALLOWED_DIRS
        ):
            continue

        for path in sorted(
            child.rglob(
                "*"
            )
        ):
            if (
                not path.is_file()
                or path.is_symlink()
            ):
                continue

            relative = path.relative_to(
                root
            )

            if _allowed_relative_path(
                relative
            ):
                yield path


def build_manifest(root):
    base = Path(
        root
    )
    result = {}

    if not base.exists():
        return result

    for path in sorted(
        base.rglob(
            "*"
        )
    ):
        if (
            not path.is_file()
            or path.is_symlink()
        ):
            continue

        relative = path.relative_to(
            base
        )

        if _allowed_relative_path(
            relative
        ):
            result[
                relative.as_posix()
            ] = _sha256(
                path
            )

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

        baseline = {}

        for source in _iter_source_files(
            instance.project_root
        ):
            relative = source.relative_to(
                instance.project_root
            )
            destination = (
                instance.workspace_root
                / relative
            )
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            shutil.copy2(
                source,
                destination,
            )
            baseline[
                relative.as_posix()
            ] = _sha256(
                source
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
