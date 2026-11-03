"""Hosted-only recursive ELF library-dependency closure audit.

Goes beyond direct DT_NEEDED checks: resolve each trusted ARM64 system
SONAME, inspect its own DT_NEEDED/RPATH and compute hashes of observed
Ubuntu-hosted ELF files. It does NOT sign or pin target-board libraries;
VENTUNO ABI, loader and filesystem permissions remain separate NO-GO gates.
Never executes audited model or native speech binaries.
"""
from collections import deque
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

from scripts.ci_native_cli_elf_audit import (
    _ALLOWED_NEEDED, _ALLOWED_INTERPRETERS, _INTERPRETER,
    _NEEDED, inspect_readelf,
)


_LDCONFIG_LINE = re.compile(
    r"^\s*([^\s()]+)\s+\(([^)]+)\)\s+=>\s+([^\s]+)\s*$"
)
_SONAME = re.compile(r"Library soname: \[([^\]]+)\]")
_UNSAFE_TAG = re.compile(r"\((RPATH|RUNPATH|AUDIT|DEPAUDIT|FILTER|AUXILIARY)\)")
_MAX_LIBRARIES = 24
_MAX_LIBRARY_BYTES = 64 * 1024 * 1024


def parse_arm64_ldconfig(output):
    """Parse native ARM64 system cache without resolving any path as code."""
    if type(output) is not str or len(output) > 2_000_000:
        raise ValueError("invalid_ldconfig_output")
    paths = {}
    for line in output.splitlines():
        match = _LDCONFIG_LINE.fullmatch(line)
        if not match:
            continue
        name, abi, raw_path = match.groups()
        if "aarch64" not in abi.casefold():
            continue
        if (not re.fullmatch(r"[A-Za-z0-9_.+-]{3,90}", name)
                or not raw_path.startswith("/")
                or len(raw_path) > 512):
            raise ValueError("invalid_ldconfig_entry")
        paths.setdefault(name, set()).add(raw_path)
    return paths


def parse_library_deps(dynamic, *, expected_soname=None):
    """Validate SONAME and reject runtime loader search/audit hooks."""
    if type(dynamic) is not str or len(dynamic) > 100_000:
        raise ValueError("invalid_dynamic_section")
    if _UNSAFE_TAG.search(dynamic):
        raise ValueError("runtime_search_or_audit_hook")
    if expected_soname is not None:
        candidates = _SONAME.findall(dynamic)
        if candidates != [expected_soname]:
            raise ValueError("unexpected_library_soname")
    needed = _NEEDED.findall(dynamic)
    if (len(needed) != len(set(needed))
            or any(not re.fullmatch(r"[A-Za-z0-9_.+-]{3,90}", s)
                   for s in needed)):
        raise ValueError("invalid_needed_sonames")
    return needed


def _readelf(path, flag):
    result = subprocess.run(
        ["readelf", flag, "--", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=6, check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C"},
    )
    if result.returncode or len(result.stdout) > 100_000:
        raise ValueError("unreadable_host_elf")
    return result.stdout


def _assert_arm64(header):
    if not all((
        re.search(r"Class:\s+ELF64\b", header),
        re.search(r"Data:\s+2's complement, little endian", header),
        re.search(r"Machine:\s+AArch64\b", header),
    )):
        raise ValueError("wrong_library_architecture")


def _library_path(name, mapping, interpreter, roots):
    if name == Path(interpreter).name:
        raw = interpreter
    else:
        matches = mapping.get(name)
        if not matches or len(matches) != 1:
            raise ValueError("missing_or_ambiguous_system_library")
        raw = next(iter(matches))
    path = Path(raw)
    if not path.is_file():
        raise ValueError("unavailable_system_library")
    actual = path.resolve(strict=True)
    if not any(root == actual.parent or root in actual.parents for root in roots):
        raise ValueError("library_outside_trusted_multiarch_roots")
    if actual.stat().st_size > _MAX_LIBRARY_BYTES:
        raise ValueError("oversized_system_library")
    return actual


def audit_recursive_closure(cli, mapping):
    """Read-only inspection of all reachable DT_NEEDED system libraries."""
    cli = Path(cli)
    header = _readelf(cli, "-h")
    program = _readelf(cli, "-l")
    dynamic = _readelf(cli, "-d")
    direct = inspect_readelf(header, program, dynamic)
    if not direct["safe"]:
        raise ValueError("untrusted_cli_direct_dependencies")
    matches = _INTERPRETER.findall(program)
    if len(matches) != 1 or matches[0] not in _ALLOWED_INTERPRETERS:
        raise ValueError("untrusted_cli_interpreter")
    interpreter = matches[0]
    allowed = _ALLOWED_NEEDED | {Path(interpreter).name}
    roots = tuple(Path(x).resolve(strict=True) for x in (
        "/usr/lib/aarch64-linux-gnu", "/lib/aarch64-linux-gnu",
    ))
    pending = deque(parse_library_deps(dynamic))
    scanned = {}
    while pending:
        name = pending.popleft()
        if name in scanned:
            continue
        if len(scanned) >= _MAX_LIBRARIES or name not in allowed:
            raise ValueError("unexpected_transitive_dependency")
        path = _library_path(name, mapping, interpreter, roots)
        _assert_arm64(_readelf(path, "-h"))
        children = parse_library_deps(
            _readelf(path, "-d"), expected_soname=name,
        )
        if any(child not in allowed for child in children):
            raise ValueError("unreviewed_transitive_soname")
        sha = hashlib.sha256()
        with path.open("rb") as handle:
            for piece in iter(lambda: handle.read(1024 * 1024), b""):
                sha.update(piece)
        scanned[name] = sha.hexdigest()
        pending.extend(children)
    if not scanned:
        raise ValueError("empty_dynamic_closure")
    # Audit digest is for this disposable runner only; not portable to VENTUNO.
    digest = hashlib.sha256()
    for name in sorted(scanned):
        digest.update(name.encode("ascii"))
        digest.update(bytes.fromhex(scanned[name]))
    return {"count": len(scanned), "host_closure_sha256": digest.hexdigest()}


def main(argv):
    if (len(argv) != 3
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"):
        return 2
    try:
        root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
        binaries = [Path(p).resolve(strict=True) for p in argv[1:]]
        if (any(root not in p.parents or not p.is_file() for p in binaries)
                or [p.name for p in binaries] != ["transcribe-cli", "whisper-cli"]):
            return 3
        ldconfig = "/sbin/ldconfig" if Path("/sbin/ldconfig").is_file() else "/usr/sbin/ldconfig"
        report = subprocess.run(
            [ldconfig, "-p"], capture_output=True, text=True,
            timeout=5, check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
        if report.returncode:
            return 4
        mapping = parse_arm64_ldconfig(report.stdout)
        if not mapping:
            return 5
        for binary in binaries:
            result = audit_recursive_closure(binary, mapping)
            print("NATIVE_HOST_CLOSURE_PASS " + binary.name
                  + " libs=" + str(result["count"])
                  + " digest=" + result["host_closure_sha256"])
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        # Only fixed internal failure reasons; do not print paths or contents.
        reason = str(error)
        if not re.fullmatch(r"[a-z_]{5,80}", reason):
            reason = "native_closure_validation_failed"
        print("NATIVE_HOST_CLOSURE_DENIED " + reason, file=sys.stderr)
        return 6


if __name__ == "__main__":
    sys.exit(main(sys.argv))
