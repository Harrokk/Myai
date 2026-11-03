"""Hosted-only recursive ARM64 ELF system-library closure check.

NO ldd, no dlopen, no executing third-party binaries. Uses readelf and
SHA-256 to inventory the transitive DT_NEEDED libraries resolved from
well-known, root-owned Ubuntu ARM64 system directories.

This checks a DISPOSABLE GitHub runner only. It does NOT establish library
provenance, GNU IFUNC/dlopen behavior or ABI safety on the VENTUNO device.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from scripts.ci_native_cli_elf_audit import (
    _ALLOWED_NEEDED, _ALLOWED_INTERPRETERS, _INTERPRETER, _NEEDED,
    inspect_readelf,
)

_SYSTEM_DIRS = (
    Path("/lib/aarch64-linux-gnu"),
    Path("/usr/lib/aarch64-linux-gnu"),
    Path("/lib"),
    Path("/usr/lib"),
)
_BAD_DYNAMIC = re.compile(
    r"\((?:RPATH|RUNPATH|AUDIT|DEPAUDIT|FILTER|AUXILIARY)\)"
)
_MACHINE = re.compile(r"Machine:\s+AArch64\b")
_CLASS = re.compile(r"Class:\s+ELF64\b")
_ENDIAN = re.compile(r"Data:\s+2's complement, little endian")
_SONAME = re.compile(r"\(SONAME\).*?\[([^\]]+)\]")
_MAX_FILE_BYTES = 128 * 1024 * 1024
_MAX_OUTPUT_BYTES = 100000
_MAX_NODES = 32


def dependency_closure(graph, *, entrypoints, trusted_loader):
    """Pure graph check: missing nodes, unknown libraries or duplicate deps deny."""
    allowed = _ALLOWED_NEEDED | {trusted_loader}
    if (type(graph) is not dict or type(entrypoints) not in (tuple, list)
            or trusted_loader not in {"ld-linux-aarch64.so.1"}
            or not entrypoints or len(graph) > _MAX_NODES):
        raise ValueError("invalid-library-graph")
    seen = set()
    pending = list(entrypoints)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        if type(name) is not str or name not in graph:
            raise ValueError("unresolved-library")
        if name not in allowed and name not in {"transcribe-cli", "whisper-cli"}:
            raise ValueError("unreviewed-library")
        deps = graph[name]
        if type(deps) not in (list, tuple) or len(deps) != len(set(deps)):
            raise ValueError("invalid-library-edges")
        if any(type(dep) is not str or dep not in allowed for dep in deps):
            raise ValueError("unreviewed-library")
        seen.add(name)
        pending.extend(deps)
        if len(seen) + len(pending) > _MAX_NODES * 4:
            raise ValueError("too-many-library-edges")
    return tuple(sorted(seen))


def _readelf(path, section):
    result = subprocess.run(
        ["readelf", section, "--", str(path)],
        capture_output=True, text=True, timeout=8,
        check=False, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
    )
    if (result.returncode != 0
            or not 0 < len(result.stdout) <= _MAX_OUTPUT_BYTES):
        raise ValueError("invalid-elf-section")
    return result.stdout


def _system_library(soname):
    if soname not in (_ALLOWED_NEEDED | {"ld-linux-aarch64.so.1"}):
        raise ValueError("unreviewed-system-soname")
    matches = set()
    for parent in _SYSTEM_DIRS:
        try:
            path = parent / soname
            resolved = path.resolve(strict=True)
            roots = [root.resolve(strict=True) for root in _SYSTEM_DIRS]
            if not any(root == resolved.parent for root in roots):
                continue
            meta = resolved.stat()
            if (not stat.S_ISREG(meta.st_mode)
                    or meta.st_uid != 0
                    or meta.st_mode & 0o022
                    or not 0 < meta.st_size <= _MAX_FILE_BYTES):
                raise ValueError("untrusted-system-file")
            matches.add(resolved)
        except FileNotFoundError:
            continue
    if len(matches) != 1:
        raise ValueError("missing-or-ambiguous-system-library")
    return matches.pop()


def _sha256_file(path):
    before = path.stat()
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    after = path.stat()
    if (before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns):
        raise ValueError("library-changed-during-hash")
    return h.hexdigest()


def inspect_system_library(path, expected_soname):
    head = _readelf(path, "-h")
    if not all(p.search(head) for p in (_MACHINE, _CLASS, _ENDIAN)):
        raise ValueError("untrusted-system-isa")
    dyn = _readelf(path, "-d")
    if _BAD_DYNAMIC.search(dyn):
        raise ValueError("untrusted-system-dynamic-search")
    found_soname = _SONAME.findall(dyn)
    if found_soname and (len(found_soname) != 1
                         or found_soname[0] != expected_soname):
        raise ValueError("system-soname-mismatch")
    needed = _NEEDED.findall(dyn)
    if len(needed) != len(set(needed)):
        raise ValueError("duplicate-system-needed")
    if any(dep not in (_ALLOWED_NEEDED | {"ld-linux-aarch64.so.1"})
           for dep in needed):
        raise ValueError("unreviewed-transitive-library")
    return needed


def audit_hosted_cli_closure(paths):
    if (os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"
            or len(paths) != 2):
        raise ValueError("hosted-arm64-only")
    root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    graph = {}
    for name, path in zip(("transcribe-cli", "whisper-cli"), paths):
        p = Path(path)
        canonical = p.resolve(strict=True)
        if (p.is_symlink() or p.name != name or canonical.parent != root / "myai-native-fullcli-bin"
                or not canonical.is_file()):
            raise ValueError("unexpected-executable-path")
        h, l, d = (_readelf(canonical, f) for f in ("-h", "-l", "-d"))
        result = inspect_readelf(h, l, d)
        if not result["safe"]:
            raise ValueError("direct-library-check-denied")
        interpreter = _INTERPRETER.findall(l)
        if len(interpreter) != 1 or interpreter[0] not in _ALLOWED_INTERPRETERS:
            raise ValueError("wrong-system-loader")
        graph[name] = result["needed"]

    to_check = set(graph["transcribe-cli"] + graph["whisper-cli"])
    actual_hashes = {}
    while to_check:
        if len(graph) > _MAX_NODES:
            raise ValueError("too-many-system-libraries")
        soname = to_check.pop()
        if soname in graph:
            continue
        path = _system_library(soname)
        deps = inspect_system_library(path, soname)
        graph[soname] = deps
        actual_hashes[soname] = _sha256_file(path)
        to_check.update(dep for dep in deps if dep not in graph)

    visited = dependency_closure(
        graph, entrypoints=("transcribe-cli", "whisper-cli"),
        trusted_loader="ld-linux-aarch64.so.1",
    )
    return {
        "libraries": tuple(sorted(actual_hashes)),
        "digests": {name: actual_hashes[name] for name in sorted(actual_hashes)},
        "nodes": visited,
    }


def main(args):
    if len(args) != 3:
        return 2
    try:
        result = audit_hosted_cli_closure(args[1:])
        # File contents, locations, audio and model names are never printed.
        # Only reviewed SONAMEs and computed SHA256 evidence are returned.
        for name, digest in result["digests"].items():
            print("AUDITED_SYSTEM_LIBRARY " + name + " sha256:" + digest)
        print("NATIVE_TRANSITIVE_ELF_CLOSURE: PASS")
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("NATIVE_TRANSITIVE_ELF_CLOSURE: DENIED", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
