# Voice writer quiescence lease — source-only DRAFT

## Problem and boundary

Previously the durable marker was fsynced before an effectful voice callback, but the journal's mutex was released **while that callback ran**. A trusted operator with a matching ticket could theoretically call `release` before the callback returned, remove the marker and later allow a second write. A process listing or bare PID check is not a reliable proof that a native action or child process has completed.

This change adds a **private, stable POSIX flock-based writer presence lease** named `runtime/.voice-active-writer.lock.v1`. The lease contains no transcript, tool name, arguments, PID, file path, results, secrets or user metadata.

## Invariant

- Guarded effectful voice tool calls obtain a **shared nonblocking lease** before creating the durable marker. They hold it through the synchronous callback, including its exceptions, Stop races, marker fsync and result handling. `run_tools` uses a scoped `ExitStack` to close this lease in a `finally` path; existing typed-text tools and safe allowlisted reads do not take it.
- `VoiceWriteReconciliation.prepare()` and `finalize()` acquire the existing stable journal mutex, then require an **exclusive nonblocking lease** on the active-writer lock. An active cooperating writer causes an explicit denial, without waiting for its callback to finish. No ticket is issued and no marker is removed. The lock inode is never unlinked.
- The active lease lock itself is opened with `O_NOFOLLOW`, owner-only permissions and `st_nlink==1` checks, then its directory entry is fsynced. A bogus link, failed fsync or unsupported POSIX locking API fails closed.
- A writer that reaches the new lease while the operator holds the exclusive release lease is denied, not queued for execution after the marker is removed. Earlier authorization is not proof of permission to execute after recovery.
- This is a **cooperative protocol across code versions**. Other code that writes effects without acquiring the lease is **not** detected, including child/grandchild processes that keep working independently after the Python callback returns. The operator must independently stop all services, worker processes and external agents; a successful lease check is not attestation of physical quiescence.

## Focused test scope

Synthetic tests use disposable project roots with no real user data, and include a second process holding the shared lease, denial of prepare/finalize, successful manual resumption after lease exit, process termination releasing a kernel flock, callback exception cleanup, and active-lock symlink denial. The change is subject to hosted x86 synthetic testing, ARM64 source-only/default-OFF check and full ARM64 project CI.

## Limits

Not an OS-wide `/proc` process census, stronger operator identity, an anti-tamper attestation, distributed locking, real eMMC power-fail test or guarantee of exact-once execution. A stale, uncooperative or old-version writer can still run after the lock is released; active native helpers must be stopped and checked by a trusted human. No real microphone, model, NPU/HTP/GenieX, board systemd/service, runner configuration, firmware or device files are changed. The branch remains stacked DRAFT.
