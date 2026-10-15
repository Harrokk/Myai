"""Experimental unprivileged CPU / virtual-memory limits for STT CHILDREN ONLY.

These are Linux/POSIX rlimits, NOT cgroups or guaranteed per-model RSS
quotas. Default values zero mean NO new resource limit. Only an
explicit, validated, opt-in isolated-STT configuration may change the
child's limits; never apply limits inside the parent/GenieX process.

RLIMIT_AS caps virtual address space, not physical RAM. FasterWhisper
and native shared libraries may reserve much more address space than
their RSS, so deployment requires separate physical model benchmarks.
"""
from __future__ import annotations

import os

CPU_ENV = "MYAI_STT_CHILD_CPU_SECONDS"
AS_ENV = "MYAI_STT_CHILD_VIRTUAL_MEMORY_MIB"
MIN_CPU_SECONDS = 5
MAX_CPU_SECONDS = 300
MIN_ADDRESS_SPACE_MIB = 1024
MAX_ADDRESS_SPACE_MIB = 8192
MIB = 1024 * 1024


def validated_limits(cpu_seconds=0, virtual_memory_mib=0):
    if (type(cpu_seconds) is not int
            or cpu_seconds != 0 and not
            MIN_CPU_SECONDS <= cpu_seconds <= MAX_CPU_SECONDS):
        raise ValueError("Invalid STT child CPU policy")
    if (type(virtual_memory_mib) is not int
            or virtual_memory_mib != 0 and not
            MIN_ADDRESS_SPACE_MIB <= virtual_memory_mib <= MAX_ADDRESS_SPACE_MIB):
        raise ValueError("Invalid STT child virtual memory policy")
    return cpu_seconds, virtual_memory_mib


def add_limit_environment(base, *, cpu_seconds=0, virtual_memory_mib=0):
    """Modify a new private subprocess env, NEVER the parent os.environ."""
    cpu_seconds, virtual_memory_mib = validated_limits(
        cpu_seconds, virtual_memory_mib,
    )
    if type(base) is not dict:
        raise ValueError("Invalid STT child environment")
    result = dict(base)
    result.pop(CPU_ENV, None)
    result.pop(AS_ENV, None)
    if cpu_seconds:
        result[CPU_ENV] = str(cpu_seconds)
    if virtual_memory_mib:
        result[AS_ENV] = str(virtual_memory_mib)
    return result


def tighten_inherited_rlimit(current, requested, infinity):
    """Never raise the inherited soft or hard resource ceiling.

    In particular, an inherited strict SOFT limit with a permissive
    HARD limit must not be raised by the STT profile. The kernel allows
    that adjustment, so relying on setrlimit() to reject it is unsafe.
    """
    if (type(current) is not tuple or len(current) != 2
            or type(requested) is not int or requested <= 0):
        raise ValueError("Invalid inherited STT resource limit")
    soft, hard = current
    if (type(soft) is not int or type(hard) is not int
            or type(infinity) is not int):
        raise ValueError("Invalid inherited STT resource limit")

    def stricter(previous):
        if previous == infinity:
            return requested
        if previous < 0:
            raise ValueError("Invalid inherited STT resource limit")
        return min(previous, requested)

    updated_soft = stricter(soft)
    updated_hard = stricter(hard)
    if updated_soft > updated_hard:
        raise ValueError("Invalid inherited STT resource limit")
    return updated_soft, updated_hard


def apply_child_limits():
    """Run only in fixed child Python worker, BEFORE native model import.

    Reject forged malformed values rather than silently skipping a cap.
    Does nothing if both variables are absent. Never writes diagnostics
    that could expose the environment, native paths or audio bytes.
    """
    raw_cpu = os.environ.get(CPU_ENV)
    raw_mem = os.environ.get(AS_ENV)
    if raw_cpu is None and raw_mem is None:
        return False
    for raw in (raw_cpu, raw_mem):
        if raw is not None and (
            not raw.isascii() or not raw.isdecimal() or len(raw) > 4
        ):
            raise ValueError("Invalid STT child resource policy")
    cpu, mem = validated_limits(
        int(raw_cpu) if raw_cpu is not None else 0,
        int(raw_mem) if raw_mem is not None else 0,
    )
    # Unix resource is imported only in the child. Read BOTH inherited
    # ceilings before making any modifications. A stricter inherited
    # SOFT limit must never be relaxed, even when its hard limit would
    # allow it. Fail closed before applying any limit if inspection
    # reveals invalid or inconsistent values.
    import resource
    changes = []
    for kind, requested in (
        (resource.RLIMIT_CPU, cpu),
        (resource.RLIMIT_AS, mem * MIB if mem else 0),
    ):
        if requested:
            current = resource.getrlimit(kind)
            changes.append((
                kind,
                tighten_inherited_rlimit(
                    current, requested, resource.RLIM_INFINITY,
                ),
            ))
    for kind, limits in changes:
        resource.setrlimit(kind, limits)
    return bool(changes)
