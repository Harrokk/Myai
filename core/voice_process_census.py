"""Linux procfs *veto* for recognisable project processes.

This is deliberately NOT proof of quiescence. Procfs may omit hidden,
reparented, unrelated-UID, remote or uninstrumented workers. No raw
argv, environment, PID, process title, or user data is persisted.
"""
import os
from pathlib import Path


_LIMIT = 32768
_ARG_LIMIT = 16384


def _read_command(path):
    with open(path, "rb") as stream:
        data = stream.read(_ARG_LIMIT + 1)
    if len(data) > _ARG_LIMIT:
        raise OSError("Incomplete procfs command line")
    return tuple(part for part in data.split(b"\x00") if part)


def _parent_pid(path):
    # Process names in /proc/PID/stat may contain spaces and parentheses.
    # Everything after the LAST ') ' begins at field 3 (state, then ppid).
    raw = path.read_bytes()
    marker = raw.rfind(b") ")
    if marker < 0:
        raise OSError("Malformed procfs process information")
    fields = raw[marker + 2:].split()
    if len(fields) < 2:
        raise OSError("Malformed procfs parent PID")
    return int(fields[1])


def _related_command(argv, root):
    if not argv:
        return False
    prefix = os.fsencode(str(root))
    for arg in argv[1:]:
        if arg == prefix or arg.startswith(prefix + b"/"):
            return True
    return False


def _related_python_module(argv, cwd, root):
    if not argv or cwd is None:
        return False
    if cwd != root and root not in cwd.parents:
        return False
    executable = os.path.basename(os.fsdecode(argv[0])).lower()
    if not executable.startswith("python"):
        return False
    for i, value in enumerate(argv[:-1]):
        if value == b"-m":
            module = argv[i + 1].decode("utf-8", "replace")
            if module.startswith(("core.", "modules.", "myai.")):
                return True
            if module in {"mail", "main", "myai"}:
                return True
    return False


def detect_project_processes(project_root, *, proc_root=Path("/proc")):
    """Return a count only; fail closed when same-UID census is unreliable.

    A positive match and its visible descendants veto operator release.
    Zero is merely 'nothing recognisable in this snapshot', NOT evidence
    that all writers were terminated.
    """
    if not hasattr(os, "geteuid"):
        raise OSError("Linux process identity API unavailable")
    root = Path(os.path.realpath(project_root))
    base = Path(proc_root)
    if not base.is_dir():
        raise OSError("Linux procfs unavailable")
    pids = {}
    count = 0
    try:
        entries = base.iterdir()
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            count += 1
            if count > _LIMIT:
                raise OSError("Procfs scan exceeded safe bound")
            pid = int(entry.name)
            if pid == os.getpid():
                continue
            try:
                info = entry.stat()
            except FileNotFoundError:
                continue  # Process terminated during census.
            except OSError as error:
                raise OSError("Procfs cannot be trusted") from error
            if info.st_uid != os.geteuid():
                continue
            try:
                ppid = _parent_pid(entry / "stat")
                argv = _read_command(entry / "cmdline")
                try:
                    cwd = Path(os.readlink(entry / "cwd")).resolve()
                except FileNotFoundError:
                    cwd = None
                except PermissionError as error:
                    raise OSError("Unreadable project process cwd") from error
            except FileNotFoundError:
                continue  # Exited during this bounded read.
            except (OSError, UnicodeError, ValueError) as error:
                raise OSError("Unverifiable local process") from error
            related = (
                _related_command(argv, root)
                or _related_python_module(argv, cwd, root)
            )
            pids[pid] = (ppid, related)
    except OSError as error:
        raise OSError("Cannot finish bounded Linux process census") from error

    active = {pid for pid, (_, related) in pids.items() if related}
    # Descendant processes can have unrelated argv or cwd.
    changed = True
    while changed:
        changed = False
        for pid, (parent, _) in pids.items():
            if pid not in active and parent in active:
                active.add(pid)
                changed = True
    return len(active)


def veto_recognised_project_processes(project_root, *, proc_root=Path("/proc")):
    if detect_project_processes(project_root, proc_root=proc_root):
        raise OSError("Recognisable MyAI process or descendant is active")
