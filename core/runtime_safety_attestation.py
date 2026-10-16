"""Minimal effective in-process safety evidence for a *future* deployment.

Snapshot is computed from the MyAIRuntimeService's loaded settings object.
Only fixed booleans, a bounded schema ID and PID are stored locally in the
normal heartbeat. No config contents, paths, secret values or env vars.
This cannot retroactively attest an already-running older version.
"""
from __future__ import annotations

import os


FLAGS = (
    ("voice", "enabled"),
    ("voice", "tts_enabled"),
    ("voice", "handsfree_enabled"),
    ("ventuno", "rpc_write_enabled"),
    ("selfdev", "enabled"),
    ("selfdev", "promotion_enabled"),
    ("geniex_supervisor", "restart_enabled"),
    ("trusted_terminals", "auto_execute"),
    ("camera", "stream_enabled"),
    ("location", "enabled"),
    ("excel", "write_enabled"),
    ("files", "write_enabled"),
)


def summarize(settings, *, pid=None):
    """Report strictly whether each expected OFF flag is literally False."""
    if pid is None:
        pid = os.getpid()
    names = {}
    for section, key in FLAGS:
        obj = settings.get(section) if isinstance(settings, dict) else None
        names[section + "_" + key + "_off"] = (
            isinstance(obj, dict) and obj.get(key) is False
        )
    memory = settings.get("memory") if isinstance(settings, dict) else None
    db = memory.get("database") if isinstance(memory, dict) else None
    names["memory_auto_save_off"] = (
        isinstance(memory, dict) and memory.get("auto_save_enabled") is False
    )
    names["isolated_test_database"] = (
        type(db) is str and db == "runtime/isolated_voice_trial/memory.db"
    )
    return {
        "schema": 1,
        "process_pid": pid if type(pid) is int and 1 <= pid < 1_000_000_000 else None,
        "voice_and_writes_off": all(names.values()),
        "checks": names,
        "credentials_exported": False,
        "device_access_performed_by_attestation": False,
    }
