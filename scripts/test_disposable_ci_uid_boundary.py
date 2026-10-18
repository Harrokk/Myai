"""Disposable Docker-only three-UID file-access regression for future MyAI CI.

Run ONLY from the dedicated GitHub-hosted, networkless, read-only-root Docker
workflow with a tmpfs /tmp. Never use physical VENTUNO users, files or keys.
This is POSIX DAC evidence, NOT real ACL/capability or GitHub runner attestation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

CI_UID = 23003
RUNTIME_UID = 23002
UPDATER_UID = 23001

# Fake values only. Their *file readability*, not content secrecy, is tested.
FAKE_JOURNAL_KEY = b"fake-ci-uid-test-journal-key"
FAKE_GITHUB_TOKEN = b"fake-ci-uid-test-github-token"


def require_disposable_container():
    if os.name != "posix" or os.geteuid() != 0:
        raise RuntimeError("Disposable container root required.")
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Not a Docker container; refusing to change UID.")
    if os.environ.get("MYAI_DISPOSABLE_UID_TEST") != "yes":
        raise RuntimeError("Disposable-only opt-in missing.")
    if not Path("/tmp").is_dir():
        raise RuntimeError("Missing volatile /tmp.")


def own(path: Path, uid: int, mode: int):
    os.chown(path, uid, uid)
    os.chmod(path, mode)


def denied(label: str, operation):
    try:
        operation()
    except PermissionError:
        return label
    raise AssertionError("Unexpected unprivileged access: " + label)


def read_public_code(root):
    code = root / "releases" / "main.py"
    assert code.read_text(encoding="utf-8") == "SAFE = True\n"


def exercise_identity(uid, root):
    assert os.geteuid() == uid
    read_public_code(root)
    private = root / "updater-private"
    key = private / "journal.key"
    verification = root / "verification" / "verification.json"
    audit = root / "audit" / "audit.jsonl"
    releases = root / "releases"
    staging = root / "staging"
    backups = root / "backups"
    memory = root / "runtime-memory" / "memory.db"
    ci = root / "ci-scratch"
    token = ci / "runner-token"
    attempts = []

    if uid == CI_UID:
        attempts.extend([
            denied("signing-key-read", key.read_bytes),
            denied("verification-read", verification.read_bytes),
            denied("verification-forge", lambda: verification.write_text("APPROVED")),
            denied("audit-read", audit.read_bytes),
            denied("audit-forge", lambda: audit.write_text("FORGED")),
            denied("memory-read", memory.read_bytes),
            denied("memory-overwrite", lambda: memory.write_text("CORRUPT")),
            denied("installed-code-write",
                   lambda: (releases / "main.py").write_text("MUTATED")),
            denied("installed-code-add", lambda: (releases / "new.py").write_text("x")),
            denied("updater-staging-write", lambda: (staging / "candidate.py").write_text("x")),
            denied("rollback-backup-write", lambda: (backups / "snapshot").write_text("x")),
        ])
        assert token.read_bytes() == FAKE_GITHUB_TOKEN
        (ci / "scratch-output").write_text("CI_ONLY\n", encoding="utf-8")
        assert (ci / "scratch-output").read_text(encoding="utf-8") == "CI_ONLY\n"
        return {"role": "ci", "denied": len(attempts), "own_scratch": True}

    if uid == RUNTIME_UID:
        attempts.extend([
            denied("runtime-signing-key-read", key.read_bytes),
            denied("runtime-verification-forge",
                   lambda: verification.write_text("APPROVED")),
            denied("runtime-code-write",
                   lambda: (releases / "main.py").write_text("MUTATED")),
            denied("runtime-updater-stage",
                   lambda: (staging / "candidate.py").write_text("x")),
            denied("runtime-ci-token-read", token.read_bytes),
        ])
        assert memory.read_bytes() == b"fake-runtime-memory-only"
        memory.write_bytes(b"fake-runtime-memory-updated")
        return {"role": "runtime", "denied": len(attempts), "own_memory": True}

    assert uid == UPDATER_UID
    attempts.extend([
        denied("updater-ci-token-read", token.read_bytes),
        denied("updater-runtime-memory-read", memory.read_bytes),
        denied("updater-runtime-memory-write", lambda: memory.write_bytes(b"BAD")),
    ])
    assert key.read_bytes() == FAKE_JOURNAL_KEY
    assert verification.read_text(encoding="utf-8") == '{"result":"unapproved"}\n'
    assert audit.read_text(encoding="utf-8") == "begin\n"
    (staging / "candidate.py").write_text("SAFE = True\n", encoding="utf-8")
    (backups / "previous.py").write_text("SAFE = True\n", encoding="utf-8")
    # Only the updater identity owns this synthetic versioned release directory.
    (releases / "new_file.py").write_text("REVIEW_ONLY = True\n", encoding="utf-8")
    with audit.open("a", encoding="utf-8") as stream:
        stream.write("disposable-updater-test\n")
    return {"role": "updater", "denied": len(attempts), "private_stage": True}


def fork_as(uid, root):
    reader, writer = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reader)
        try:
            os.setgroups([])
            os.setgid(uid)
            os.setuid(uid)
            answer = exercise_identity(uid, root)
            os.write(writer, json.dumps(answer).encode("ascii"))
            os._exit(0)
        except BaseException as error:
            # Do not copy exception message, file paths or private values to logs.
            os.write(writer, type(error).__name__.encode("ascii", "replace"))
            os._exit(1)
    os.close(writer)
    result = bytearray()
    while len(result) < 4096:
        chunk = os.read(reader, 4096 - len(result))
        if not chunk:
            break
        result.extend(chunk)
    os.close(reader)
    _, status = os.waitpid(pid, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AssertionError("Disposable identity test failed: "
                             + result.decode("ascii", "replace")[:64])
    return json.loads(result.decode("ascii"))


def prepare():
    root = Path(tempfile.mkdtemp(prefix="myai-three-uid-", dir="/tmp"))
    root.chmod(0o755)
    directories = (
        ("releases", UPDATER_UID, 0o755),
        ("updater-private", UPDATER_UID, 0o700),
        ("verification", UPDATER_UID, 0o700),
        ("audit", UPDATER_UID, 0o700),
        ("staging", UPDATER_UID, 0o700),
        ("backups", UPDATER_UID, 0o700),
        ("runtime-memory", RUNTIME_UID, 0o700),
        ("ci-scratch", CI_UID, 0o700),
    )
    for name, _, _ in directories:
        (root / name).mkdir()
    files = (
        ("releases/main.py", UPDATER_UID, 0o444, b"SAFE = True\n"),
        ("updater-private/journal.key", UPDATER_UID, 0o600, FAKE_JOURNAL_KEY),
        ("verification/verification.json", UPDATER_UID, 0o600,
         b'{"result":"unapproved"}\n'),
        ("audit/audit.jsonl", UPDATER_UID, 0o600, b"begin\n"),
        ("runtime-memory/memory.db", RUNTIME_UID, 0o600, b"fake-runtime-memory-only"),
        ("ci-scratch/runner-token", CI_UID, 0o600, FAKE_GITHUB_TOKEN),
    )
    for name, uid, mode, data in files:
        path = root / name
        path.write_bytes(data)
        own(path, uid, mode)
    # Narrow access AFTER all privileged fixture creation.
    for name, uid, mode in directories:
        own(root / name, uid, mode)
    return root


def main():
    require_disposable_container()
    root = prepare()
    # Run as three distinct real Linux numeric UIDs inside the disposable
    # container, not mocked euid. No host account or project tree is mounted.
    results = [fork_as(uid, root) for uid in (CI_UID, RUNTIME_UID, UPDATER_UID)]
    assert [r["role"] for r in results] == ["ci", "runtime", "updater"]
    assert results[0]["denied"] == 11
    assert results[1]["denied"] == 5
    assert results[2]["denied"] == 3
    print(json.dumps({
        "status": "PASS", "isolated_linux_uids": 3,
        "denied_cross_identity_operations": 19,
        "production_touched": False,
        "real_ventuno_acl_or_runner_policy_proven": False,
        "real_verifier_signing_proven": False,
        "physical_hardware_tests_authorized": False,
        "production_deployment_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
