import difflib
import os
import stat

from core.selfdev_workspace import _manifest_open_flags, _manifest_parts


_MAX_REVIEW_FILE_BYTES = 2 * 1024 * 1024
_MAX_REVIEW_TOTAL_BYTES = 8 * 1024 * 1024
_MAX_REVIEW_FILE_LINES = 20_000


def _read_lines(root, relative, *, allow_missing=False):
    """Read one permitted regular file from a pinned no-follow directory.

    Absent files are allowed only for expected additions/deletions. A
    concurrent symlink swap must fail rather than disclose an outside file.
    """
    parts = _manifest_parts(relative)
    directory_flags, file_flags = _manifest_open_flags()
    directory_fd = os.open(root, directory_flags)
    try:
        try:
            for part in parts[:-1]:
                child_fd = os.open(part, directory_flags, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = child_fd
            file_fd = os.open(parts[-1], file_flags, dir_fd=directory_fd)
        except FileNotFoundError:
            if allow_missing:
                return [], 0
            raise

        try:
            original = os.fstat(file_fd)
            if not stat.S_ISREG(original.st_mode) or original.st_nlink != 1:
                raise PermissionError("Selfdev-granskning kräver en vanlig ensam fil.")
            if original.st_size > _MAX_REVIEW_FILE_BYTES:
                raise ValueError("Selfdev-granskningens filstorleksgräns överskreds.")
            with os.fdopen(file_fd, "rb") as handle:
                file_fd = -1
                contents = handle.read(_MAX_REVIEW_FILE_BYTES + 1)
                if len(contents) > _MAX_REVIEW_FILE_BYTES:
                    raise ValueError(
                        "Selfdev-granskningens filstorleksgräns överskreds."
                    )
                after = os.fstat(handle.fileno())
                if (
                    len(contents) != original.st_size
                    or after.st_dev != original.st_dev
                    or after.st_ino != original.st_ino
                    or after.st_size != original.st_size
                    or after.st_mtime_ns != original.st_mtime_ns
                    or after.st_ctime_ns != original.st_ctime_ns
                ):
                    raise RuntimeError(
                        "Selfdev-filen ändrades under granskningen."
                    )
        finally:
            if file_fd >= 0:
                os.close(file_fd)
    finally:
        os.close(directory_fd)

    lines = contents.decode("utf-8").splitlines(keepends=True)
    if len(lines) > _MAX_REVIEW_FILE_LINES:
        raise ValueError("Selfdev-granskningen har för många filrader.")
    return lines, len(contents)


def build_selfdev_review(
    workspace,
    *,
    max_diff_chars=100_000,
):
    if not isinstance(max_diff_chars, int) or max_diff_chars <= 0:
        raise ValueError("max_diff_chars måste vara ett positivt heltal.")

    changes = workspace.changed_files()
    paths = sorted(
        changes["changed"] + changes["added"] + changes["deleted"]
    )
    sections = []
    total_source_bytes = 0

    for relative in paths:
        before, before_bytes = _read_lines(
            workspace.project_root,
            relative,
            allow_missing=relative in changes["added"],
        )
        after, after_bytes = _read_lines(
            workspace.workspace_root,
            relative,
            allow_missing=relative in changes["deleted"],
        )
        total_source_bytes += before_bytes + after_bytes
        if total_source_bytes > _MAX_REVIEW_TOTAL_BYTES:
            raise ValueError(
                "Selfdev-granskningens totala datagräns överskreds."
            )

        diff = "".join(
            difflib.unified_diff(
                before,
                after,
                fromfile="active/" + relative,
                tofile="staging/" + relative,
            )
        )
        if diff:
            sections.append(diff)

    combined = "\n".join(sections)
    truncated = False
    if len(combined) > max_diff_chars:
        combined = combined[:max_diff_chars]
        combined += "\n... [diff trunkerad]"
        truncated = True

    verification = None
    try:
        verification = workspace.read_verification()
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, RuntimeError):
        verification = {
            "passed": False,
            "error": "verification.json kunde inte läsas",
        }

    return {
        "session_id": workspace.session_id,
        "changed": changes["changed"],
        "added": changes["added"],
        "deleted": changes["deleted"],
        "source_drift": workspace.source_drift(),
        "verification": verification,
        "diff": combined,
        "diff_truncated": truncated,
    }
