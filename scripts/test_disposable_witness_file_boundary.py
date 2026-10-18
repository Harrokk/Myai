"""DISPOSABLE Docker UID test: witness-owned atomic file storage (NO signing).

This demonstrates Linux DAC against three other simulated service UIDs and
best-effort rename/fsync. It does NOT prove power-loss durability, protected
monotonic hardware, real signing keys or deployed service isolation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

WITNESS_UID = 23005
OTHER_UIDS = (23001, 23002, 23003)
_TEST_CONTENT = (b'{"synthetic_signed_head":"genesis"}\n',
                 b'{"synthetic_signed_head":"advanced"}\n')


def require_disposable_docker():
    if (os.name != "posix" or os.geteuid() != 0
            or not Path("/.dockerenv").is_file()
            or os.environ.get("MYAI_DISPOSABLE_WITNESS_TEST") != "yes"):
        raise RuntimeError("Refuse outside explicit disposable Docker root")


def drop(uid):
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)
    if os.geteuid() != uid:
        raise RuntimeError("UID drop failed")


def child(fn, *args):
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            result = fn(*args)
            os.write(write_fd, json.dumps(result, sort_keys=True).encode("ascii"))
            os._exit(0)
        except BaseException as error:
            os.write(write_fd, type(error).__name__.encode("ascii","replace"))
            os._exit(1)
    os.close(write_fd)
    return pid, read_fd


def collect(pid, read_fd):
    message = os.read(read_fd, 1024)
    os.close(read_fd)
    _, status = os.waitpid(pid, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AssertionError("Disposable witness child failed: "
                             + message.decode("ascii", "replace")[:70])
    return json.loads(message)


def witness_write(private_dir, version):
    drop(WITNESS_UID)
    assert private_dir.stat().st_uid == WITNESS_UID
    assert private_dir.stat().st_mode & 0o777 == 0o700
    data = _TEST_CONTENT[version]
    temporary = private_dir / "pending-head"
    final = private_dir / "signed-head.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, final)
    dir_fd = os.open(private_dir, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    if final.read_bytes() != data or final.stat().st_mode & 0o777 != 0o600:
        raise AssertionError("Witness private file content or DAC changed")
    return {
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "revision": version + 1,
        "writer_uid": os.geteuid(),
        "atomic_rename_called": True,
        "file_and_directory_fsync_called": True,
    }


def unauthorized_access(private_dir, uid):
    drop(uid)
    final = private_dir / "signed-head.json"
    denied = 0
    fd, source_path = tempfile.mkstemp(prefix="myai-witness-attack-", dir="/tmp")
    os.close(fd)
    try:
        for operation in (
            lambda: final.read_bytes(),
            lambda: final.write_bytes(b"FORGED"),
            lambda: (private_dir / "pending-head").write_bytes(b"FORGED"),
            lambda: os.replace(source_path, final),
        ):
            try:
                operation()
            except PermissionError:
                denied += 1
            else:
                raise AssertionError("Other UID accessed witness private storage")
    finally:
        if Path(source_path).exists():
            Path(source_path).unlink()
    return {"uid": os.geteuid(), "permission_denials": denied}


def main():
    require_disposable_docker()
    root = Path(tempfile.mkdtemp(prefix="myai-witness-dac-", dir="/tmp"))
    root.chmod(0o755)
    private = root / "external-witness"
    private.mkdir()
    os.chown(private, WITNESS_UID, WITNESS_UID)
    private.chmod(0o700)
    first = collect(*child(witness_write, private, 0))
    denied = [collect(*child(unauthorized_access, private, uid))
              for uid in OTHER_UIDS]
    updated = collect(*child(witness_write, private, 1))
    second_denied = [collect(*child(unauthorized_access, private, uid))
                     for uid in OTHER_UIDS]
    assert first["writer_uid"] == updated["writer_uid"] == WITNESS_UID
    assert updated["revision"] == 2
    assert updated["content_sha256"] != first["content_sha256"]
    assert all(result["permission_denials"] == 4
               for result in denied + second_denied)
    assert first["file_and_directory_fsync_called"]
    assert updated["file_and_directory_fsync_called"]
    print(json.dumps({
        "status": "PASS",
        "disposable_only": True,
        "independent_witness_uid": WITNESS_UID,
        "other_service_uids_denied": len(OTHER_UIDS),
        "kernel_dac_denials": sum(result["permission_denials"]
                                  for result in denied + second_denied),
        "atomic_replace_and_fsync_exercised": True,
        "test_witness_contents_are_synthetic_unsigned": True,
        "witness_cryptographic_signature_tested_here": False,
        "physical_power_loss_durability_proven": False,
        "independent_monotonic_hardware_storage_implemented": False,
        "production_deployment_authorized": False,
        "ventuno_touched": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
