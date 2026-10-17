import os
import re
import errno
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path

from core.audit_log import (
    AuditLogger,
    audit_outcome_for_exception,
)
from core.config import PROJECT_ROOT, load_settings


DEFAULT_ALLOWED_WRITE_EXTENSIONS = {".txt", ".md", ".csv", ".json"}


def _config(settings=None):
    settings = settings or load_settings()
    return settings.get("files", {})


def workspace_root(settings=None):
    config = _config(settings)
    raw = config.get("workspace_root", "runtime/workspace")
    path = Path(raw)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def _normalize_user_path(value):
    text = str(value or "").strip().strip('"').strip("'")

    if not text:
        raise ValueError("Ingen filsökväg angavs.")

    if re.match(r"^[A-Za-z]:[\\/]", text):
        raise ValueError("Absoluta sökvägar är inte tillåtna i workspace.")

    if text.startswith(("/", "\\", "~")):
        raise ValueError("Absoluta sökvägar är inte tillåtna i workspace.")

    return text.replace("\\", "/")


def resolve_workspace_path(value, settings=None):
    root = workspace_root(settings)
    relative = _normalize_user_path(value)
    candidate = (root / relative).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "Sökvägen försöker lämna det tillåtna workspace."
        ) from error

    return candidate


def _safe_parts(value):
    """Lexical user path components; never use resolved pathnames for I/O."""
    relative = _normalize_user_path(value)
    parts = relative.split("/")
    if any(part in {"", ".", ".."} or chr(0) in part for part in parts):
        raise ValueError("Sökvägen försöker lämna det tillåtna workspace.")
    return tuple(parts)


@contextmanager
def _anchored_parent(user_path, settings, *, create=False):
    """Pin every Linux directory inode; reject symlinks on every hop.

    All later file operations use the final opened directory fd, not a
    pathname reconstructed after a check. The configured workspace root
    and its ancestors must be operator-trusted.
    """
    parts = _safe_parts(user_path)
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if not all(hasattr(os, key) for key in required):
        raise RuntimeError("Säker filåtkomst kräver Linux dir_fd/O_NOFOLLOW.")

    root = workspace_root(settings)
    if create:
        root.mkdir(parents=True, exist_ok=True)

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    directory_fd = os.open(root, flags)
    try:
        for part in parts[:-1]:
            try:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=directory_fd)
                    except FileExistsError:
                        pass
                new_fd = os.open(part, flags, dir_fd=directory_fd)
            except OSError as error:
                if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise PermissionError(
                        "Symboliska länkar är inte tillåtna i workspace."
                    ) from error
                raise
            os.close(directory_fd)
            directory_fd = new_fd

        yield directory_fd, parts[-1], "/".join(parts)
    finally:
        os.close(directory_fd)


def extract_file_path(user_text):
    text = str(user_text or "")

    quoted = re.search(
        r'["“”\']([^"“”\']+\.[A-Za-z0-9]{1,12})["“”\']',
        text,
    )

    if quoted:
        return quoted.group(1).strip()

    token = re.search(
        r'(?<![\w/])([A-Za-z0-9_.\-/\\]+\.[A-Za-z0-9]{1,12})(?!\w)',
        text,
    )

    if token:
        return token.group(1).strip()

    return None


def extract_write_content(user_text):
    text = str(user_text or "")
    patterns = (
        r"med\s+innehållet\s*[:\-]?\s*(.+)$",
        r"med\s+texten\s*[:\-]?\s*(.+)$",
        r"innehåll\s*:\s*(.+)$",
        r"text\s*:\s*(.+)$",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match:
            return match.group(1).strip()

    path = extract_file_path(text)

    if path:
        position = text.find(path)
        colon = text.find(":", position + len(path))

        if colon >= 0:
            return text[colon + 1:].strip()

    return None


def _ensure_enabled(settings=None):
    config = _config(settings)

    if not config.get("enabled", True):
        raise RuntimeError("Filverktygen är avstängda i konfigurationen.")

    return config


def list_workspace_files(settings=None):
    config = _ensure_enabled(settings)
    root = workspace_root(settings)
    root.mkdir(parents=True, exist_ok=True)

    try:
        max_entries = int(config.get("max_list_entries", 100))
    except (TypeError, ValueError) as error:
        raise ValueError("files.max_list_entries måste vara ett heltal.") from error

    if max_entries <= 0:
        raise ValueError("files.max_list_entries måste vara större än 0.")

    def sorted_files(directory):
        # Sort one directory at a time rather than building and sorting
        # the entire workspace tree before applying max_list_entries.
        # Include "/" when ordering directories to preserve full-path sort.
        with os.scandir(directory) as scan:
            children = sorted(
                scan,
                key=lambda entry: (
                    entry.name.lower()
                    + ("/" if entry.is_dir(follow_symlinks=False) else "")
                ),
            )
        for child in children:
            if child.is_symlink():
                continue
            path = Path(child.path)
            try:
                path.resolve(strict=True).relative_to(root)
            except (OSError, RuntimeError, ValueError):
                continue
            if child.is_file(follow_symlinks=False):
                yield path
            elif child.is_dir(follow_symlinks=False):
                yield from sorted_files(path)

    entries = []
    for path in sorted_files(root):
        try:
            size = path.stat().st_size
        except (OSError, RuntimeError):
            continue
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": size,
            }
        )
        if len(entries) >= max_entries:
            break

    return entries


def read_workspace_text(user_path, settings=None):
    config = _ensure_enabled(settings)

    try:
        max_chars = int(config.get("max_read_chars", 20000))
    except (TypeError, ValueError) as error:
        raise ValueError("files.max_read_chars måste vara ett heltal.") from error

    if max_chars <= 0:
        raise ValueError("files.max_read_chars måste vara större än 0.")

    # A descriptor-relative O_NOFOLLOW open prevents a parent/final symlink
    # swap between validation and use. O_NONBLOCK prevents a swapped FIFO
    # from hanging the assistant before its regular-file check.
    visible = []
    kept_chars = 0
    total_chars = 0
    with _anchored_parent(user_path, settings) as (directory_fd, filename, relative):
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(filename, flags, dir_fd=directory_fd)
        except OSError as error:
            if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise PermissionError(
                    "Symboliska länkar är inte tillåtna i workspace."
                ) from error
            raise

        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("Endast vanliga textfiler får läsas i workspace.")
            try:
                with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                    descriptor = -1  # fdopen owns the descriptor
                    while True:
                        block = handle.read(16_384)
                        if not block:
                            break
                        total_chars += len(block)
                        if kept_chars < max_chars:
                            excerpt = block[: max_chars - kept_chars]
                            visible.append(excerpt)
                            kept_chars += len(excerpt)
            except UnicodeDecodeError as error:
                raise ValueError(
                    "Filen är inte en UTF-8-textfil och kan inte läsas "
                    "med detta textverktyg."
                ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    return {
        "path": relative,
        "content": "".join(visible),
        "truncated": total_chars > max_chars,
        "total_chars": total_chars,
    }

def write_workspace_text(user_path, content, settings=None):
    config = _ensure_enabled(settings)

    if not config.get("write_enabled", False):
        raise RuntimeError(
            "Skrivning i workspace är avstängd i konfigurationen."
        )

    allowed = config.get(
        "allowed_write_extensions",
        sorted(DEFAULT_ALLOWED_WRITE_EXTENSIONS),
    )
    allowed = {
        str(extension).lower()
        if str(extension).startswith(".")
        else "." + str(extension).lower()
        for extension in allowed
    }

    parts = _safe_parts(user_path)
    suffix = Path(parts[-1]).suffix.lower()
    if suffix not in allowed:
        raise ValueError(
            f"Filtypen {suffix or '(utan ändelse)'} är inte "
            "tillåten för allmän workspace-skrivning."
        )

    text = str(content)
    if not text:
        raise ValueError("Tomt filinnehåll skrivs inte utan uttrycklig text.")

    with _anchored_parent(user_path, settings, create=True) as (
        directory_fd, filename, relative
    ):
        # Fail closed on an existing symlink or non-file. If an attacker
        # swaps the target AFTER this check, descriptor-relative os.replace
        # replaces only that directory entry, never follows the symlink.
        try:
            existing = os.stat(
                filename, dir_fd=directory_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise PermissionError("Målfilen måste vara en vanlig fil.")

        # Random, exclusive staging in the SAME pinned directory inode.
        # Only relative names plus dir_fd are passed to os.replace/unlink.
        temporary = "." + filename + "." + secrets.token_hex(12) + ".tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(
                temporary, filename,
                src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
            )
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise

    return {
        "path": relative,
        "chars_written": len(text),
    }

def workspace_list(user_text=""):
    try:
        entries = list_workspace_files()

        if not entries:
            return "Workspace är tomt."

        lines = [f"Filer i workspace: {len(entries)}"]

        for item in entries:
            lines.append(
                f"- {item['path']} ({item['size_bytes']} byte)"
            )

        return "\n".join(lines)
    except Exception as error:
        return "Kunde inte lista workspace: feltext dold."


def workspace_read(user_text):
    try:
        path = extract_file_path(user_text)

        if not path:
            return (
                "Jag hittar inget filnamn i instruktionen. "
                'Ange till exempel: Läs filen "anteckning.txt".'
            )

        result = read_workspace_text(path)
        suffix = (
            "\n[Innehållet är trunkerat.]"
            if result["truncated"]
            else ""
        )

        return (
            f"Innehåll i {result['path']}:\n"
            f"{result['content']}"
            f"{suffix}"
        )
    except Exception as error:
        return "Kunde inte läsa filen: feltext dold."


def workspace_write(user_text):
    audit = None
    target = None

    try:
        path = extract_file_path(user_text)
        content = extract_write_content(user_text)

        if not path:
            return (
                "Jag hittar inget filnamn i instruktionen. "
                'Ange till exempel: Skapa filen "anteckning.txt" '
                "med innehållet Hej."
            )

        if content is None:
            return (
                "Jag hittar inget tydligt filinnehåll. "
                'Använd till exempel: Skapa filen "anteckning.txt" '
                "med innehållet Hej."
            )

        settings = load_settings()
        audit = AuditLogger(
            settings,
            PROJECT_ROOT,
        )
        target = str(
            path
        )
        audit.write_attempt(
            action="workspace_write",
            component="files.workspace",
            target=target,
            details={
                "chars": len(
                    str(
                        content
                    )
                ),
            },
        )

        result = write_workspace_text(
            path,
            content,
            settings=settings,
        )
        audit.write_result(
            action="workspace_write",
            component="files.workspace",
            outcome="success",
            target=result[
                "path"
            ],
            details={
                "chars": result[
                    "chars_written"
                ],
            },
        )
        return (
            f"Filen {result['path']} sparades i workspace "
            f"({result['chars_written']} tecken)."
        )
    except Exception as error:
        if audit is not None:
            audit.write_result(
                action="workspace_write",
                component="files.workspace",
                outcome=(
                    audit_outcome_for_exception(
                        error
                    )
                ),
                target=target,
                details={
                    "error_type": type(
                        error
                    ).__name__,
                },
            )

        return "Kunde inte skriva filen: feltext dold."


TOOLS = {
    "workspace_list": {
        "function": workspace_list,
        "description": (
            "Listar filer i MyAI:s sandboxade lokala workspace."
        ),
        "pass_user_input": True,
    },
    "workspace_read": {
        "function": workspace_read,
        "description": (
            "Läser en namngiven UTF-8-textfil inne i MyAI:s sandboxade "
            "workspace."
        ),
        "pass_user_input": True,
    },
    "workspace_write": {
        "function": workspace_write,
        "result_failure_prefixes": ("Kunde inte skriva filen:",),
        "description": (
            "Skapar eller skriver en tillåten textfil inne i MyAI:s "
            "sandboxade workspace när skrivning uttryckligen är aktiverad."
        ),
        "pass_user_input": True,
        "safety": {
            "effect": "write",
            "voice_confirmation_required": True,
        },
    },
}
