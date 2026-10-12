"""Read-only provenance evidence from the live GenieX systemd service.

Only reads systemd MainPID, /proc comm/exe basename, maps library basenames,
and open FastRPC device links. Does not read cmdline/environ or credentials,
does not inspect model buffers, does not attach a debugger or alter services.

Mapped QNN libraries and FastRPC descriptors indicate an active backend,
NOT a measured graph execution sequence, HTP usage, or context load order.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections import deque
from pathlib import Path

SERVICE = "myai-geniex.service"
LIBRARIES = (
    "libQnnHtp.so",
    "libQnnHtpV75Stub.so",
    "libQnnSystem.so",
    "libcdsprpc.so",
)
MAX_PROCESSES = 24
MAX_CHILDREN_BYTES = 4096
MAX_MAPS_BYTES = 8 * 1024 * 1024
MAX_FDS = 512


def parse_main_pid(text: str) -> int | None:
    """Reject missing, anomalous, or forged PID values."""
    clean = text.strip()
    if not re.fullmatch(r"[1-9][0-9]{0,9}", clean):
        return None
    pid = int(clean)
    return pid if pid > 1 else None


def main_pid_from_systemd() -> int | None:
    try:
        result = subprocess.run(
            ["systemctl", "show", SERVICE, "--property=MainPID", "--value"],
            capture_output=True, text=True, errors="replace", timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    return parse_main_pid(result.stdout)


def bounded_children(proc_root: Path, pid: int) -> list[int]:
    target = proc_root / str(pid) / "task" / str(pid) / "children"
    try:
        with target.open("rb") as handle:
            payload = handle.read(MAX_CHILDREN_BYTES + 1)
    except OSError:
        return []
    if len(payload) > MAX_CHILDREN_BYTES:
        return []
    return [
        int(word) for word in payload.decode("ascii", errors="replace").split()[:MAX_PROCESSES]
        if re.fullmatch(r"[1-9][0-9]{0,9}", word) and int(word) > 1
    ]


def service_tree(proc_root: Path, main_pid: int) -> list[int]:
    """Limit traversal to systemd's actual service PID and its descendants."""
    queue = deque([main_pid])
    visited: set[int] = set()
    while queue and len(visited) < MAX_PROCESSES:
        pid = queue.popleft()
        if pid in visited or pid <= 1:
            continue
        visited.add(pid)
        for child in bounded_children(proc_root, pid):
            if child not in visited and len(queue) < MAX_PROCESSES:
                queue.append(child)
    return sorted(visited)


def is_geniex_process(proc_root: Path, pid: int) -> bool:
    root = proc_root / str(pid)
    try:
        with (root / "comm").open("r", encoding="utf-8", errors="replace") as stream:
            comm = stream.read(100).strip().lower()
    except OSError:
        comm = ""
    try:
        executable = os.path.basename(os.readlink(root / "exe")).lower()
    except OSError:
        executable = ""
    return "geniex" in comm or "geniex" in executable


def classify_maps(contents: str) -> dict[str, bool]:
    """Match library file BASENAMES, not arbitrary mapped paths or contents."""
    observed = set()
    for line in contents.splitlines():
        filename = line.rsplit(maxsplit=1)[-1] if line.strip() else ""
        basename = filename.rsplit("/", 1)[-1]
        if basename in LIBRARIES:
            observed.add(basename)
    return {name: name in observed for name in LIBRARIES}


def process_evidence(proc_root: Path, pid: int) -> dict[str, object]:
    root = proc_root / str(pid)
    result: dict[str, object] = {
        "maps_readable": False,
        "mapped_libraries": {name: False for name in LIBRARIES},
        "fast_rpc_secure_fd_open": False,
        "fd_scan_capped": False,
        "fd_readable": False,
    }
    try:
        with (root / "maps").open("rb") as stream:
            contents = stream.read(MAX_MAPS_BYTES + 1)
        if len(contents) <= MAX_MAPS_BYTES:
            result["mapped_libraries"] = classify_maps(
                contents.decode("utf-8", errors="replace")
            )
            result["maps_readable"] = True
    except OSError:
        pass
    try:
        with os.scandir(root / "fd") as entries:
            count = 0
            result["fd_readable"] = True
            for entry in entries:
                count += 1
                if count > MAX_FDS:
                    result["fd_scan_capped"] = True
                    break
                try:
                    destination = os.readlink(entry.path)
                except OSError:
                    continue
                if destination == "/dev/fastrpc-cdsp-secure":
                    result["fast_rpc_secure_fd_open"] = True
    except OSError:
        pass
    return result


def summarize_service(proc_root: Path, main_pid: int | None) -> dict[str, object]:
    base: dict[str, object] = {
        "status": "inconclusive-no-mainpid",
        "service_mainpid_present": False,
        "geniex_process_count": 0,
        "mapped_libraries": {name: False for name in LIBRARIES},
        "fast_rpc_secure_fd_open": False,
        "complete_process_maps": False,
        "runtime_backend_evidence": False,
        "actual_context_order_proven": False,
        "actual_graph_execution_proven": False,
        "direct_htp_profiling_verified": False,
        "service_changes_allowed": False,
    }
    if main_pid is None or not (proc_root / str(main_pid)).is_dir():
        return base
    base["service_mainpid_present"] = True
    pids = service_tree(proc_root, main_pid)
    matching = [pid for pid in pids if is_geniex_process(proc_root, pid)]
    base["geniex_process_count"] = len(matching)
    if not matching:
        base["status"] = "inconclusive-no-geniex-child"
        return base
    observations = [process_evidence(proc_root, pid) for pid in matching]
    base["mapped_libraries"] = {
        name: any(o["mapped_libraries"][name] for o in observations)
        for name in LIBRARIES
    }
    base["fast_rpc_secure_fd_open"] = any(
        o["fast_rpc_secure_fd_open"] for o in observations
    )
    base["complete_process_maps"] = all(o["maps_readable"] for o in observations)
    base["runtime_backend_evidence"] = bool(
        base["mapped_libraries"]["libQnnHtp.so"]
        and base["fast_rpc_secure_fd_open"]
    )
    base["status"] = ("backend-associated-with-service"
                      if base["runtime_backend_evidence"]
                      else "inconclusive-backend-association")
    return base


def main() -> int:
    print("Live GenieX service backend attestation (read-only)")
    print(json.dumps(summarize_service(Path("/proc"), main_pid_from_systemd()),
                     sort_keys=True))
    print("No model context buffers inspected; runtime graph order remains unverified.")
    print("No tracing, inference, service interruption, or secondary model started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
