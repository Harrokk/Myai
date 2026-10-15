"""Linux-only, fail-closed cleanup of an owned STT process group.

All callers MUST launch the fixed checked-in STT worker with
start_new_session=True; group ID then equals its child's original PID.
The leader can exit while native/helper descendants remain alive.
Checking proc.poll() is therefore NOT a sufficient cleanup test.

This is NOT a Linux cgroup or subreaper: a helper intentionally using
setsid()/setpgid() to escape the original group cannot be guaranteed
terminated by this helper. Those scenarios require separately reviewed
cgroup-based containment before production activation.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import time

# Only short, fixed cleanup budgets. Stop can fail closed if the kernel
# cannot reap a child or its descendants within this budget.
GROUP_REAP_SECONDS = 1.5


def _live_group_members(group_id):
    """True if a NON-ZOMBIE process still belongs to the owned process group.

    False means no runnable/sleeping member seen. None means we could
    not inspect the Linux process table reliably (fail closed).
    This only looks at kernel state/IDs; it never exports /proc cmdlines,
    tokens, environment variables, process paths or private logs.
    """
    if type(group_id) is not int or group_id <= 0:
        return None
    try:
        with os.scandir("/proc") as entries:
            for entry in entries:
                if not entry.name.isascii() or not entry.name.isdigit():
                    continue
                try:
                    stat = Path("/proc") .joinpath(entry.name, "stat").read_bytes()
                except FileNotFoundError:
                    # A concurrent exit during enumeration is expected.
                    continue
                except OSError:
                    return None
                suffix = stat.rsplit(b") ", 1)
                if len(suffix) != 2:
                    return None
                fields = suffix[1].split()
                if len(fields) < 3:
                    return None
                try:
                    pgid = int(fields[2])
                except ValueError:
                    return None
                if pgid == group_id and fields[0] not in {b"Z", b"X", b"x"}:
                    return True
    except OSError:
        return None
    return False


def terminate_owned_group(proc, *, cleanup_seconds=GROUP_REAP_SECONDS):
    """Kill group EVEN WHEN THE LEADER ALREADY EXITED, reap, verify.

    Never send a signal to the runner's own group; refuse if the caller
    passed something other than its independently created child group.
    On any error, callers must retain the original proc handle and
    block further native-model launches until cleanup is confirmed.
    """
    if proc is None:
        return
    pgid = getattr(proc, "pid", None)
    if type(pgid) is not int or pgid <= 1 or pgid == os.getpgrp():
        raise RuntimeError("Isolated STT process cleanup incomplete")

    # Before signaling an already-exited leader, check whether group
    # survivors exist; this also avoids signaling a vanished/reused PGID.
    # Do not call proc.poll() to skip cleanup: poll is only leader state.
    state = _live_group_members(pgid)
    if state is None:
        raise RuntimeError("Isolated STT process cleanup incomplete")
    if state:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            raise RuntimeError("Isolated STT process cleanup incomplete") from None

    try:
        proc.wait(timeout=cleanup_seconds)
    except (subprocess.TimeoutExpired, OSError):
        raise RuntimeError("Isolated STT process cleanup incomplete") from None

    deadline = time.monotonic() + cleanup_seconds
    while True:
        state = _live_group_members(pgid)
        if state is False:
            break
        if state is None or time.monotonic() >= deadline:
            raise RuntimeError("Isolated STT process cleanup incomplete")
        time.sleep(0.05)

    # Streams are closed only after the group is confirmed inert.
    for name in ("stdin", "stdout"):
        stream = getattr(proc, name, None)
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
