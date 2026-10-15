# Crash-injection review: offline operator reconciliation — DRAFT

**2026-10-15.** Stack base: DRAFT PR #231. Tests are synthetic subprocesses in disposable directories, not a real mains-power removal or live device recovery procedure.

## What was unsafe in the prior state?

The prior operator `finalize()` created and synced a private receipt hard link, removed its pending-ticket name and then removed the durable write marker. A crash **between** those operations could leave (a) a pending ticket with two hard links, or (b) a receipt with no pending-ticket name while the marker was still present. An ordinary repeat of `finalize()` would fail to read the ticket, leaving the previously reviewed marker permanently blocked without a safe documented continuation. That failure is conservative but impractical.

## New fail-closed resumed release

An operator must use the **same 128-bit review ticket** and type the **same exact external-verification attestation again**. There is no automatic recovery action and no new voice command.

The recovery function checks the private marker and its stable file identity (`st_dev`, `st_ino`, `st_ctime_ns`). Three states are recognized:

1. **Pending ticket has one link:** normal flow; make a private no-overwrite receipt hard link, sync the directory, remove pending name and sync, remove marker and sync
2. **Pending ticket and receipt are two names for the same two-link inode:** resume after the first receipt link; require exact bytes, owner, permissions, marker identity and matching inode/dev before syncing and continuing
3. **Pending name is missing but private one-link receipt is present:** resume after pending removal; require exact receipt bytes and marker identity, sync the directory, then remove marker and sync

Unknown, inconsistent, tampered or unreadable states **deny release**. A damaged ticket created during an even earlier crash cannot be silently replaced. The operator must explicitly inspect and use a separate future privileged maintenance procedure for anything outside the safe states.

## Crash-injection matrix

The targeted tests spawn isolated child Python processes and call `os._exit()` **immediately after** each selected operation, without Python cleanup:

| Injected point | Marker expected immediately after child death | Safe manual continuation |
| --- | --- | --- |
| After hard linking receipt | Present | Verify same ticket + marker, resume |
| After receipt directory fsync | Present | Verify same ticket + marker, resume |
| After unlinking pending name | Present | Verify durable receipt, resume |
| After pending unlink directory fsync | Present | Verify durable receipt, resume |
| After unlinking marker | Absent; receipt remains | No retry of external effect |
| After final directory fsync | Absent; receipt remains | No retry of external effect |
| After creating pending ticket but before writing its contents | Present | Fail closed; manual maintenance needed |
| Final directory fsync returns failure after marker unlink | Marker may already be absent | Report uncertain outcome; inspect receipt and marker, never claim still blocked |

The crash tests **do not simulate loss of device power, controller write-cache rollback, malicious same-UID process interference, POSIX locking on an NFS filesystem, eMMC endurance, STT or NPU activity**, or a real operator's external verification. They establish only local-process interruption behavior with a trusted filesystem and disposable test contents.

## Review outcome / remaining gates

Two focused passes were performed: (1) ordering, crash/reentry cases and lock ownership, (2) privacy, malformed private files, UI error messaging and accidental automatic retries. No raw voice transcripts, arguments, results or live user files enter the ticket or receipt. Recovery remains a local TTY-only human decision outside the MyAI voice tool registry. A storage error after unlinking the marker now produces an **uncertain** message, not the false guarantee that the marker still exists.

Remaining before actual use: independent security review, review of six earlier static call-site warnings, tested process termination/absence of active writers, trusted local POSIX storage power-loss behavior, crash recovery in an isolated physical test window, and authorization to operate the actual board. All functions remain source-only/DRAFT.
