"""DISPOSABLE CONTAINER ONLY: exercise two POSIX UIDs in /tmp.

This script refuses to run outside a container, never touches host accounts,
systemd, production code, live MyAI, microphones or real secret material.
"""

import json
import os
from pathlib import Path
import stat
import tempfile


RUNTIME_UID = 23002
UPDATER_UID = 23001


def _must_be_disposable_container():
    if os.name != "posix" or os.geteuid() != 0:
        raise RuntimeError("Requires isolated Linux container root.")
    # Docker container marker in this specific disposable CI workflow.
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Refusing UID operations outside Docker.")
    if os.environ.get("MYAI_DISPOSABLE_UID_TEST") != "yes":
        raise RuntimeError("Explicit disposable-only gate is missing.")


def _own(path, owner, mode):
    os.chown(path, owner, owner)
    os.chmod(path, mode)


def _deny(operation, label):
    try:
        operation()
    except PermissionError:
        return
    raise AssertionError(f"Unexpected permission: {label}")


def _run_identity(identity, root):
    assert os.geteuid() == identity
    release = root / "releases"
    source = release / "main.py"
    key = root / "protected" / "journal.key"
    stage = root / "stage"
    audit = root / "audit" / "audit.jsonl"

    assert source.read_text(encoding="utf-8") == "SAFE = True\n"
    if identity == RUNTIME_UID:
        _deny(lambda: key.read_bytes(), "read updater key")
        _deny(lambda: source.write_text("MUTATED", encoding="utf-8"), "edit code")
        _deny(lambda: (release / "added.py").write_text("x"), "publish code")
        _deny(lambda: (stage / "candidate.py").write_text("x"), "write staging")
        _deny(lambda: audit.read_text(encoding="utf-8"), "read privileged audit")
        _deny(lambda: audit.write_text("FORGED"), "forge privileged audit")
        return {"identity": "runtime", "protected": True}

    assert identity == UPDATER_UID
    assert key.read_bytes() == b"fake-container-only-key"
    (stage / "candidate.py").write_text("SAFE = False\n", encoding="utf-8")
    (release / "new_file.py").write_text("CANDIDATE = True\n", encoding="utf-8")
    with audit.open("a", encoding="utf-8") as stream:
        stream.write("updater-test\n")
    return {"identity": "updater", "allowed": True}


def _fork_as(identity, root):
    reader, writer = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reader)
        try:
            os.setgroups([])
            os.setgid(identity)
            os.setuid(identity)
            result = _run_identity(identity, root)
            os.write(writer, json.dumps(result).encode("utf-8"))
            os._exit(0)
        except BaseException as error:
            os.write(writer, repr(error).encode("utf-8"))
            os._exit(1)
    os.close(writer)
    message = b""
    while True:
        chunk = os.read(reader, 4096)
        if not chunk:
            break
        message += chunk
    os.close(reader)
    _, status = os.waitpid(pid, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AssertionError(f"UID {identity} failed: {message!r}")
    return json.loads(message.decode("utf-8"))


def main():
    _must_be_disposable_container()
    # No cleanup is needed: Docker --rm discards the private volatile /tmp
    # mount. Root deliberately has NO CAP_DAC_OVERRIDE, so it cannot enter
    # updater-owned 0700 directories after permissions are finalized.
    root = Path(tempfile.mkdtemp(prefix="myai-disposable-uid-"))
    os.chmod(root, 0o755)
    release = root / "releases"
    protected = root / "protected"
    stage = root / "stage"
    audit_dir = root / "audit"
    directories = (
        (release, 0o755),
        (protected, 0o700),
        (stage, 0o700),
        (audit_dir, 0o700),
    )
    for directory, _mode in directories:
        directory.mkdir()
    # Initialize fake files BEFORE restricting their parent directories.
    source = release / "main.py"
    source.write_text("SAFE = True\n", encoding="utf-8")
    _own(source, UPDATER_UID, 0o444)
    secret = protected / "journal.key"
    secret.write_bytes(b"fake-container-only-key")
    _own(secret, UPDATER_UID, 0o600)
    audit = audit_dir / "audit.jsonl"
    audit.write_text("begin\n", encoding="utf-8")
    _own(audit, UPDATER_UID, 0o600)
    for directory, mode in directories:
        _own(directory, UPDATER_UID, mode)

    runtime = _fork_as(RUNTIME_UID, root)
    updater = _fork_as(UPDATER_UID, root)
    assert runtime["protected"] is True
    assert updater["allowed"] is True
    assert source.read_text(encoding="utf-8") == "SAFE = True\n"
    print(json.dumps({
        "status": "PASS",
        "runtime": "denied_privileged_write_read",
        "updater": "simulated_permissions_only",
        "production_touched": False,
        "container_discarded": True,
    }))

if __name__ == "__main__":
    main()
