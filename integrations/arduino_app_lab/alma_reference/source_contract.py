"""Pinned operator-provided Alma App Lab ZIP audit and final-event adapter.

No model loading, archive extraction, microphone access, socket connection,
secret creation, voice synthesis or service startup. Source-only: never calls
the installed VENTUNO application. Actual caller ownership and audio release
must be verified separately before a physical integration.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import stat
import threading
import unicodedata
import zipfile
from pathlib import Path

ZIP_SHA256 = "3fe9070939603e6383f95f2a99b92e56eef6c665942d0e161db39d3f85234ec8"
ROOT = "Local-LLM-Piper-Alma-NoKeyword/"
# SHA256s of exactly the 13 files in the operator's personally tested archive.
# Binary ONNX weights are intentionally not committed to the MyAI repository.
FILES = {
    "README.md": ("77feaf1c8a1fd93d0ed4a394b1289183dd7422f7721ca43afdd0c86536dbd0ab", 2674),
    "app.yaml": ("aa1f64cb80bfb3601c9707220d090cd1f5a45c97c7e04b4ac80258775192b883", 206),
    "bricks/piper_sv_tts/__init__.py": ("225aa143f1669813eea254b6f3111a94cb9357d01be9de10e1cf177716276cdd", 1747),
    "bricks/piper_sv_tts/brick_compose.yaml": ("60ead671d1e113af4f40969327870b1add4b07ad8fe247f58f8c893de3619d4f", 583),
    "bricks/piper_sv_tts/brick_config.yaml": ("bc889bfde574ebbda068a2fe1a774852236e54e7f20b8d272e64ded057e4f3f6", 36),
    "bricks/piper_sv_tts/container/Dockerfile": ("2873bdc6c1b208734d83b22d1884550803f246ca838b976dca8f83a37a5987a2", 439),
    "bricks/piper_sv_tts/container/models/MODEL_CARD": ("a7f67ea437d91f32aea15268e7604488ff0f6f93e04a7e2136e29c7e80406105", 536),
    "bricks/piper_sv_tts/container/models/sv_SE-alma-medium.onnx": ("b4bfecd22e30cf28f514eeea06c0da440be1721435a652d0571ee65963ce8f65", 63434611),
    "bricks/piper_sv_tts/container/models/sv_SE-alma-medium.onnx.json": ("f7467e5d2ada0239004fca552f42b25ac90a92b848e5c283aec13a1f26a85f84", 3907),
    "bricks/piper_sv_tts/container/server.py": ("fbf638c1537884afa7691c7c36dc42cb10ff6c45db4ade284ed1e117a6f91b3a", 3177),
    "python/main.py": ("f1d3f3e2ecc94197f3a452f1a13029f41c7778046d14dc28d7346c87c06f2a87", 6468),
    "sketch/sketch.ino": ("e49db9c307e208185af2c2361d08d5df3652852e72849186865800ed5f7871b2", 3263),
    "sketch/sketch.yaml": ("e09f4afe03f6a07f8e5b0c03e8c48767e6b1841bf4496df77060fa5a71c1040c", 106),
}
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 75 * 1024 * 1024
FRAME_DOMAIN = b"MyAI-AppLab-FinalText-2026-11-13\x00"
MAX_TEXT_CHARS = 500


def _file_digest(path):
    checksum = hashlib.sha256()
    with open(path, "rb") as stream:
        while block := stream.read(1024 * 1024):
            checksum.update(block)
    return checksum.hexdigest()


def verify_operator_archive(path):
    """Check exact operator-tested source and voice weights; never extract."""
    path = Path(path)
    if (not path.is_file() or path.is_symlink()
            or path.stat().st_size > MAX_ARCHIVE_BYTES):
        raise ValueError("Expected the approved regular App Lab archive")
    if not hmac.compare_digest(_file_digest(path), ZIP_SHA256):
        raise ValueError("Not the exact operator-tested Alma archive")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) != len(FILES):
                raise ValueError("Unexpected archive entry count")
            if sum(i.file_size for i in entries) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Archive is oversized")
            names = {i.filename for i in entries}
            if len(names) != len(entries) or names != {ROOT + n for n in FILES}:
                raise ValueError("Unexpected or repeated archive paths")
            for info in entries:
                # Never trust archive paths or Unix link metadata.
                if (info.flag_bits & 1 or info.is_dir()
                        or info.filename.startswith("/")
                        or ".." in info.filename.split("/")
                        or (info.create_system == 3 and stat.S_ISLNK(info.external_attr >> 16))):
                    raise ValueError("Unsafe archive metadata")
                expected_hash, expected_size = FILES[info.filename[len(ROOT):]]
                if info.file_size != expected_size:
                    raise ValueError("Archive member size mismatch")
                checksum = hashlib.sha256()
                count = 0
                with archive.open(info) as reader:
                    while chunk := reader.read(1024 * 1024):
                        count += len(chunk)
                        if count > expected_size:
                            raise ValueError("Oversized archive member")
                        checksum.update(chunk)
                if count != expected_size or not hmac.compare_digest(checksum.hexdigest(), expected_hash):
                    raise ValueError("Archive member hash mismatch")
    except (zipfile.BadZipFile, EOFError, OSError) as error:
        raise ValueError("Unreadable Alma archive") from error
    return {
        "status": "exact-archive-verified",
        "files_verified": len(FILES),
        "app_main_sha256": FILES["python/main.py"][0],
        "alma_weights_sha256": FILES["bricks/piper_sv_tts/container/models/sv_SE-alma-medium.onnx"][0],
    }


def _valid_text(text):
    return (
        type(text) is str
        and 0 < len(text.strip()) <= MAX_TEXT_CHARS
        and len(text) <= MAX_TEXT_CHARS
        and all(unicodedata.category(c) not in {"Cc", "Cf", "Cs"}
                for c in text)
    )


class AlmaFinalASRGate:
    """Consume real Arduino stream event types; forward only a full final.

    The operator's working application accepts a partial-text fallback for
    its own conversational Qwen. That fallback is NOT trusted for MyAI tools.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._consumed = False
        self._final = None
        self._final_seen = False
        self._partial_seen = False

    def feed(self, event):
        with self._lock:
            if self._consumed or self._final_seen:
                return False
            kind = getattr(event, "type", None)
            if kind == "partial_text":
                # A partial transcript is never eligible for tool dispatch.
                self._partial_seen = True
                return False
            if kind != "full_text":
                return False
            self._final_seen = True
            text = getattr(event, "data", None)
            if not _valid_text(text):
                return False
            self._final = text.strip()
            return True

    def take_final(self, *, session_active=False, asr_released=False,
                   stop_requested=None):
        with self._lock:
            if self._consumed:
                return None
            self._consumed = True
            value = self._final
        if (session_active is not True or asr_released is not True
                or not callable(stop_requested)):
            return None
        try:
            if stop_requested() is not False:
                return None
        except BaseException:
            return None
        return value


def sign_final_for_myai(text, *, secret, session_id, request_id, issued_at):
    """Portable App Lab request encoding; no sockets or credentials installed.

    Future trusted caller must manage session keys, IDs, ASR release and the
    actual connection. The HMAC layout matches MyAI's source-only server.
    """
    import re
    if type(secret) is not bytes or len(secret) != 32:
        raise ValueError("Private session key required")
    if (type(session_id) is not str or re.fullmatch("[0-9a-f]{32}", session_id) is None
            or type(request_id) is not str or re.fullmatch("[0-9a-f]{32}", request_id) is None
            or type(issued_at) is not int or issued_at < 0
            or not _valid_text(text)):
        raise ValueError("Invalid final ASR request")
    body = {
        "version": 1, "action": "submit_final", "session_id": session_id,
        "request_id": request_id, "issued_at": issued_at, "text": text,
    }
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    body["mac"] = hmac.new(secret, FRAME_DOMAIN + canonical,
                           hashlib.sha256).hexdigest()
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    if not 0 < len(encoded) <= 2048:
        raise ValueError("Final ASR request exceeds IPC frame")
    return encoded
