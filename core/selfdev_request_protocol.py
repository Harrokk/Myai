"""Inspection-only admission protocol for a future privilege-separated updater.

This module is deliberately PURE: no filesystem, process, network, Git or
production selfdev operations. A syntactically valid request is NEVER an
authorization to deploy, recover, install or change a service.
"""

from dataclasses import dataclass
import hashlib
import json
import re
import time

from core.selfdev_workspace import _allowed_relative_path


_MAX_MESSAGE_BYTES = 32 * 1024
_MAX_FILES = 32
_MAX_PATH_CHARS = 160
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_EXPIRY_SECONDS = 300
_LOWER_HEX_32 = re.compile(r"^[0-9a-f]{32}$")
_LOWER_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_LOWER_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass(frozen=True)
class InspectionRequest:
    """A bounded request to inspect bytes only, never a promotion grant."""

    request_id: str
    revision: str
    expires_unix: int
    file_hashes: tuple[tuple[str, str], ...]
    request_digest: str
    action: str = "inspect_candidate"
    requires_human_approval: bool = True
    authorizes_mutation: bool = False


@dataclass(frozen=True)
class InspectionReport:
    request_id: str
    status: str
    inspected_files: int
    requires_human_approval: bool = True
    authorizes_mutation: bool = False


def _no_duplicate_fields(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("Duplicate JSON field is forbidden.")
        record[key] = value
    return record


def _invalid_constant(value):
    raise ValueError("Nonfinite JSON constants are forbidden.")


def _exact_fields(value, names, label):
    if type(value) is not dict or set(value) != names:
        raise ValueError("Invalid or extra fields in " + label + ".")


def _valid_source_path(value):
    if (
        type(value) is not str
        or not 1 <= len(value) <= _MAX_PATH_CHARS
        or not _PATH.fullmatch(value)
        or "//" in value
        or any(part in (".", "..") or part.startswith(".")
               for part in value.split("/"))
        or not _allowed_relative_path(value)
    ):
        raise ValueError("Source path not admitted for inspection.")
    return value


def parse_inspection_request(message, *, now_unix=None):
    """Parse and canonicalize untrusted bytes into an inspection-only object.

    Caller MUST independently authenticate its transport and inspect actual
    source provenance. No approval token is accepted by this parser.
    """
    if type(message) is not bytes or len(message) > _MAX_MESSAGE_BYTES:
        raise ValueError("Request must be bounded UTF-8 bytes.")
    try:
        data = json.loads(
            message.decode("utf-8"),
            object_pairs_hook=_no_duplicate_fields,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("Malformed inspection request.") from error

    _exact_fields(
        data,
        {"version", "action", "request_id", "revision",
         "expires_unix", "files"},
        "request",
    )
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("Unsupported inspection protocol version.")
    if data["action"] != "inspect_candidate":
        raise ValueError("Only nonmutating candidate inspection is available.")
    request_id = data["request_id"]
    revision = data["revision"]
    if type(request_id) is not str or not _LOWER_HEX_32.fullmatch(request_id):
        raise ValueError("Invalid request identifier.")
    if type(revision) is not str or not _LOWER_HEX_40.fullmatch(revision):
        raise ValueError("Invalid pinned Git revision.")
    expires = data["expires_unix"]
    if type(expires) is not int:
        raise ValueError("Expiry must be an integer Unix timestamp.")
    now = int(time.time()) if now_unix is None else now_unix
    if type(now) is not int or now < 0:
        raise ValueError("Invalid inspection clock.")
    if not now < expires <= now + _MAX_EXPIRY_SECONDS:
        raise ValueError("Expired or excessive request lifetime.")

    files = data["files"]
    if type(files) is not list or not 1 <= len(files) <= _MAX_FILES:
        raise ValueError("Invalid manifest file count.")
    pairs = []
    seen_casefold = set()
    for item in files:
        _exact_fields(item, {"path", "sha256"}, "manifest item")
        path = _valid_source_path(item["path"])
        expected = item["sha256"]
        if type(expected) is not str or not _LOWER_HEX_64.fullmatch(expected):
            raise ValueError("Invalid SHA-256 manifest hash.")
        if path.casefold() in seen_casefold:
            raise ValueError("Ambiguous or duplicate manifest path.")
        seen_casefold.add(path.casefold())
        pairs.append((path, expected))
    if pairs != sorted(pairs):
        raise ValueError("Manifest paths must be in canonical order.")

    canonical = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return InspectionRequest(
        request_id=request_id,
        revision=revision,
        expires_unix=expires,
        file_hashes=tuple(pairs),
        request_digest=hashlib.sha256(canonical).hexdigest(),
    )


def compare_supplied_bytes(request, contents):
    """Compare caller-supplied in-memory bytes; NEVER open or mutate files.

    Matching content is not a trust decision about its origin, signature,
    user authorization, on-device installation or replay resistance.
    """
    if type(request) is not InspectionRequest or type(contents) is not dict:
        raise TypeError("Inspection request and content map are required.")
    paths = {p for p, _ in request.file_hashes}
    if set(contents) != paths:
        return InspectionReport(request.request_id, "blocked_manifest_mismatch", 0)
    inspected = 0
    for path, expected in request.file_hashes:
        content = contents[path]
        if type(content) is not bytes or len(content) > _MAX_FILE_BYTES:
            return InspectionReport(request.request_id, "blocked_invalid_bytes", inspected)
        inspected += 1
        if hashlib.sha256(content).hexdigest() != expected:
            return InspectionReport(request.request_id, "blocked_hash_mismatch", inspected)
    return InspectionReport(request.request_id, "bytes_match_untrusted", inspected)
