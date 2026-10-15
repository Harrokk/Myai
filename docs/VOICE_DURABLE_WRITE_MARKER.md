# Durable voice write marker — source-only DRAFT

This is a deliberately conservative write-ahead safety barrier for effectful voice tools. It does **not** establish exactly-once execution, idempotency of a payment or file write, an audited recovery database or durable completion receipts.

## Before an effectful callback

After a guarded voice plan passes whole-batch and live authorization, but **before** invoking an effectful tool, `MyAICore` calls `VoiceWriteAheadMarker.begin_effect()`. The fixed marker `runtime/voice-write-unreconciled.v1` is created in the trusted project root using `O_CREAT|O_EXCL|O_NOFOLLOW`, file permissions `0600`, directory checks against symlinks, foreign ownership and group/world writable directories. The process writes only the fixed format identifier `MYAI-VOICE-WRITE-UNRECONCILED-v1`, `fsync()`s the marker and its directory, and **only then** may start the tool callback.

No raw tool name, user text, arguments, path from a request, timestamps identifying a user, HMAC, token, result, audit error, or microphone data is included in the marker. Git ignores the whole `runtime/` folder. Storage failures, existing marker files, malformed paths and non-local/untrusted journal directory conditions fail closed rather than running a tool without its safety marker. A previously written marker remains even when the callback reports success: execution, durable effects and user delivery are not one atomic transaction.

When two processes use the same trusted project root and local POSIX filesystem, the exclusive marker makes only one newly marked writer eligible to start. If the process crashes after the file is synced, a new `MyAICore` reads the existing marker and refuses effectful voice tools. **A new core instance and Stop→Start cannot clear it.** Safe allowlisted status reads remain available. A regular typed-text command retains its preexisting tool behavior and is not protected by this voice-only journal.

This version intentionally blocks **a second effectful tool within the same voice plan** after the first marker. A plan requiring two writes must be redesigned as one transactional adapter with its own idempotency guarantees, not by bypassing the marker.

## Manual reconciliation

The assistant may show only a fixed explanation that previous changes could remain and the safe boolean `manual_reconciliation_required`. It must never read out raw tool arguments or supply an automatic retry/replay. To recover, a **trusted human outside the voice interface** must inspect the actual external target, record whether the change occurred, ensure no old worker is still running, and deliberately clear the marker only under separately authorized maintenance procedures. This DRAFT intentionally provides **no** voice command, API or unattended action to clear the marker.

The marker stores no receipts and cannot determine whether an effect succeeded, failed or was duplicated. Deleting it without verifying the external state reintroduces the duplicate-write risk. Markers cannot be safely kept in a mutable or remote network filesystem without a separate distributed coordination/transaction design.

## Limitations / verification

`fsync` and exclusive creation protect common local-filesystem crash/restart paths; they cannot guarantee hardware power-fail durability on arbitrary storage devices or prevent a separate tool or text interface from making an equivalent change. Root-level attackers and untrusted processes with write access to the journal directory remain outside the guarantee. Full read-only source tests exercise process restart, synthetic child crash, exclusive marker collisions, symlink denial and simulated fsync failure. No actual microphone, native FasterWhisper, HTP/NPU, GenieX, USB, firmware, systemd or active MyAI service is enabled or modified. Full user-authorized hardware evaluation is required before production deployment.
