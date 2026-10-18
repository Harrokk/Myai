"""Test-only fixed Bubblewrap observation contract, never selfdev promotion.

Only a trusted test fixture supplied from an isolated, disposable host is
inspected; no runtime-supplied commands, paths, flags or success assertions.
Bubblewrap must *actually execute* and its real network namespace must differ
from its caller's; no fallback to host execution is permitted.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from core.selfdev_bounded_runner import run_bounded


FIXTURE = b"SAFE = 1\n"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE).hexdigest()
PLAN_SHA256 = hashlib.sha256(b"MyAI/disposable-bwrap-fixed-ast-v1").hexdigest()
_TEST_SCRIPT = (
    "import ast,hashlib,json,os,pathlib;"
    "p=pathlib.Path('/workspace/fixture.py');"
    "b=p.read_bytes();"
    "ast.parse(b.decode('ascii'),filename='<fixed-bwrap-fixture>');"
    "fd=p.open('ab') if False else None;"
    "refused=False;"
    "\ntry:\n p.write_bytes(b'FORGED')\n"
    "except OSError:\n refused=True\n"
    "assert refused;"
    "d=hashlib.sha256(b).hexdigest();"
    "net=os.stat('/proc/self/ns/net').st_ino;"
    "print(json.dumps({'fixture_sha256':d,'net_namespace_inode':net,"
    "'file_mutation_denied':refused},sort_keys=True))"
)
MAX_STDOUT = 512
LIMIT_SECONDS = 6


@dataclass(frozen=True)
class BubblewrapObservation:
    fixture_sha256: str
    plan_sha256: str
    sandbox: str = "bubblewrap"
    network_isolated: bool = True
    host_devices_exposed: bool = False
    verifier_execution_observed_on_disposable_host: bool = True
    independent_production_verifier_implemented: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def build_command(*, bwrap, trusted_fixture_root, python="/usr/bin/python3"):
    """Use fixed code and fixed read-only mounts, no caller-supplied payload."""
    if bwrap != "/usr/bin/bwrap" or python != "/usr/bin/python3":
        raise ValueError("Unapproved test executables")
    root = Path(trusted_fixture_root)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("Fixture must have absolute canonical path")
    if root.is_symlink() or not root.is_dir():
        raise PermissionError("Untrusted fixture directory")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise PermissionError("Fixture ownership mismatch")
    if info.st_mode & 0o077:
        raise PermissionError("Fixture must be private")
    fixture = root / "fixture.py"
    file_info = fixture.lstat()
    if (not stat.S_ISREG(file_info.st_mode)
            or file_info.st_uid != os.geteuid()
            or file_info.st_mode & 0o022):
        raise PermissionError("Untrusted source fixture mode/owner")
    if fixture.read_bytes() != FIXTURE:
        raise ValueError("Changed test fixture")
    cmd = [
        "/usr/bin/bwrap", "--die-with-parent", "--new-session",
        "--unshare-all", "--clearenv",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
    ]
    for system_root in ("/usr", "/bin", "/lib", "/lib64", "/etc"):
        if Path(system_root).exists():
            cmd.extend(["--ro-bind", system_root, system_root])
    cmd.extend([
        "--ro-bind", str(root), "/workspace",
        "--chdir", "/workspace",
        "--setenv", "HOME", "/tmp",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", "LC_ALL", "C",
        "/usr/bin/python3", "-I", "-B", "-c", _TEST_SCRIPT,
    ])
    return cmd


def observe(*, trusted_fixture_root, bwrap="/usr/bin/bwrap",
            runner=run_bounded, host_ns_inode=None):
    """Fail closed if Bubblewrap cannot establish namespaces or run test."""
    command = build_command(bwrap=bwrap, trusted_fixture_root=trusted_fixture_root)
    host_inode = (os.stat("/proc/self/ns/net").st_ino
                  if host_ns_inode is None else host_ns_inode)
    if type(host_inode) is not int or host_inode <= 0:
        raise ValueError("Invalid host network namespace")
    result = runner(
        command, timeout=LIMIT_SECONDS,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LC_ALL": "C",
             "PYTHONDONTWRITEBYTECODE": "1"},
        max_output_bytes=4096,
    )
    if (type(result.returncode) is not int
            or result.returncode != 0
            or type(result.stderr) is not str or result.stderr
            or type(result.stdout) is not str
            or len(result.stdout) > MAX_STDOUT):
        raise RuntimeError("Real Bubblewrap verification failed")
    try:
        item = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Invalid sandbox result") from exc
    if (type(item) is not dict
            or set(item) != {"fixture_sha256", "net_namespace_inode",
                             "file_mutation_denied"}
            or item["fixture_sha256"] != FIXTURE_SHA256
            or type(item["net_namespace_inode"]) is not int
            or item["net_namespace_inode"] <= 0
            or item["net_namespace_inode"] == host_inode
            or item["file_mutation_denied"] is not True):
        raise RuntimeError("Sandbox network/read-only observation not proved")
    return BubblewrapObservation(FIXTURE_SHA256, PLAN_SHA256)
