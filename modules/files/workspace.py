import os
import re
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

    entries = []

    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file():
            continue

        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
            }
        )

        if len(entries) >= max_entries:
            break

    return entries


def read_workspace_text(user_path, settings=None):
    config = _ensure_enabled(settings)
    path = resolve_workspace_path(user_path, settings)

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(
            f"Filen finns inte i workspace: {user_path}"
        )

    try:
        max_chars = int(config.get("max_read_chars", 20000))
    except (TypeError, ValueError) as error:
        raise ValueError("files.max_read_chars måste vara ett heltal.") from error

    if max_chars <= 0:
        raise ValueError("files.max_read_chars måste vara större än 0.")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(
            "Filen är inte en UTF-8-textfil och kan inte läsas "
            "med detta textverktyg."
        ) from error

    truncated = len(content) > max_chars

    return {
        "path": path.relative_to(workspace_root(settings)).as_posix(),
        "content": content[:max_chars],
        "truncated": truncated,
        "total_chars": len(content),
    }


def write_workspace_text(user_path, content, settings=None):
    config = _ensure_enabled(settings)

    if not config.get("write_enabled", False):
        raise RuntimeError(
            "Skrivning i workspace är avstängd i konfigurationen."
        )

    path = resolve_workspace_path(user_path, settings)
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

    if path.suffix.lower() not in allowed:
        raise ValueError(
            f"Filtypen {path.suffix or '(utan ändelse)'} är inte "
            "tillåten för allmän workspace-skrivning."
        )

    text = str(content)

    if not text:
        raise ValueError("Tomt filinnehåll skrivs inte utan uttrycklig text.")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)

    return {
        "path": path.relative_to(workspace_root(settings)).as_posix(),
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
        return f"Kunde inte lista workspace: {error}"


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
        return f"Kunde inte läsa filen: {error}"


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

        return f"Kunde inte skriva filen: {error}"


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
