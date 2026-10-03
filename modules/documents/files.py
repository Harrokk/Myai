from pathlib import Path

from core.config import PROJECT_ROOT


DOCUMENT_ROOT = PROJECT_ROOT / "runtime" / "documents"
ALLOWED_TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv"}
MAX_WRITE_CHARS = 1_000_000
DEFAULT_READ_CHARS = 12_000
MAX_READ_CHARS = 100_000


def _safe_text_path(filename):
    value = (filename or "").strip().replace("\\", "/")

    if not value:
        raise ValueError("Filnamn saknas.")

    relative = Path(value)

    if relative.is_absolute():
        raise ValueError("Absoluta sökvägar är inte tillåtna.")

    first_part = relative.parts[0] if relative.parts else ""

    if ":" in first_part:
        raise ValueError("Enhetsbeteckning i sökvägen är inte tillåten.")

    suffix = relative.suffix.lower()

    if suffix not in ALLOWED_TEXT_SUFFIXES:
        raise ValueError(
            "Tillåten filtyp är .txt, .md, .json eller .csv."
        )

    root = DOCUMENT_ROOT.resolve()
    candidate = (root / relative).resolve()

    if candidate != root and root not in candidate.parents:
        raise ValueError("Sökvägen lämnar den tillåtna dokumentmappen.")

    return candidate


def _validate_text_content(content):
    if not isinstance(content, str):
        raise ValueError("Filinnehåll måste vara text.")

    if len(content) > MAX_WRITE_CHARS:
        raise ValueError(
            f"Texten är för stor. Max {MAX_WRITE_CHARS} tecken per skrivning."
        )

    return content


def text_file_write(
    filename,
    content,
    overwrite=False,
):
    path = _safe_text_path(filename)
    text = _validate_text_content(content)

    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Filen finns redan: {path.name}. "
            "Sätt overwrite=true för att ersätta den."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    return (
        f"Textfil sparad: {path} | "
        f"{len(text)} tecken"
    )


def text_file_read(
    filename,
    max_chars=DEFAULT_READ_CHARS,
):
    path = _safe_text_path(filename)

    if not path.exists():
        raise FileNotFoundError(f"Textfilen finns inte: {path.name}")

    limit = max(1, min(int(max_chars), MAX_READ_CHARS))
    text = path.read_text(encoding="utf-8")

    if len(text) <= limit:
        return text

    return (
        text[:limit]
        + f"\n\n... [avkortat efter {limit} tecken]"
    )


def text_file_append(filename, content):
    path = _safe_text_path(filename)
    text = _validate_text_content(content)

    if not path.exists():
        raise FileNotFoundError(
            f"Textfilen finns inte: {path.name}"
        )

    with path.open("a", encoding="utf-8") as file:
        file.write(text)

    return (
        f"Text tillagd i {path.name}: "
        f"{len(text)} tecken"
    )


def document_list():
    root = DOCUMENT_ROOT

    if not root.exists():
        return "Dokumentmappen är tom."

    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
    )

    if not files:
        return "Dokumentmappen är tom."

    lines = ["Lokala dokument:"]

    for path in files[:100]:
        relative = path.relative_to(root)
        lines.append(f"- {relative}")

    if len(files) > 100:
        lines.append(
            f"... {len(files) - 100} ytterligare filer visas inte."
        )

    return "\n".join(lines)


TOOLS = {
    "text_file_write": {
        "function": text_file_write,
        "description": (
            "Skapar en lokal text-, Markdown-, JSON- eller CSV-fil under "
            "runtime/documents. Skriver inte över en befintlig fil utan "
            "uttryckligt overwrite."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
            "required": ["filename", "content"],
            "additionalProperties": False,
        },
    },
    "text_file_read": {
        "function": text_file_read,
        "description": (
            "Läser en lokal text-, Markdown-, JSON- eller CSV-fil under "
            "runtime/documents med en säker maximal svarslängd."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            "required": ["filename"],
            "additionalProperties": False,
        },
    },
    "text_file_append": {
        "function": text_file_append,
        "description": (
            "Lägger till text i en befintlig lokal text-, Markdown-, JSON- "
            "eller CSV-fil under runtime/documents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["filename", "content"],
            "additionalProperties": False,
        },
    },
    "document_list": {
        "function": document_list,
        "description": (
            "Listar lokala dokument under runtime/documents utan att ändra dem."
        ),
    },
}
