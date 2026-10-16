# Operator process-census veto — source-only DRAFT

This is a **supplemental negative safety gate**, not proof that all processes stopped. It builds on stacked DRAFT PR #233's active-writer flock lease. No actual VENTUNO runtime, microphone, HTP/NPU, live process or external file is touched in the tests.

## Intended threat

An older MyAI process without the new writer lease can remain alive after Stop. It may have native subprocesses or Python helpers that did not inherit a managed flock. An offline operator's valid review receipt is NOT proof that all these effectful workers stopped.

Before both `prepare()` and `finalize()` and while holding the journal/recovery locks, the code now performs a bounded Linux `/proc` process census. It **denies** the operation when recognisable same-UID processes using paths rooted in the configured project or an identifiable MyAI Python module still exist, or when visible children/descendants of such a process are running. Unreadable or incomplete procfs data for same-UID processes fails closed. This is independent of (and additive to) the writer lease.

The operator can use the read-only diagnostic `python -m scripts.voice_write_reconcile --project-root /TRUSTED/MYAI processes`. It prints only a count, and explicitly warns that zero matches **DO NOT** establish quiescence. No raw command lines, environment variables, PIDs, credentials, process titles or input transcripts are saved to the receipt, printed or exposed through voice.

## Important limitations

- A procfs snapshot is **not atomic** with external native IO. Processes may start, exit, or change their parentage during/between snapshots. A daemonized grandchild reparented outside the detected tree, a worker with unrelated arguments/cwd, processes running under different OS users, a separate machine, a container with a different PID namespace or an uninstrumented external service may not be recognised.
- Project-root path arguments and Python module/cwd combinations are *heuristics*, not cryptographic process identity. They may cause false positives (safely blocking manual release) and false negatives (never providing proof of safety). No automatic process termination or process-ID reuse based unlocking is implemented.
- The procfs check is performed while the existing journal mutex and exclusive cooperative writer lock are held. New **cooperating** tools cannot begin during this check. A non-cooperating old tool can still race with it. An operator must STOP and independently confirm all service, process-group, child-helper, and external effects before any release.
- The release routine intentionally fails closed on platforms without trusted POSIX APIs or Linux procfs. This is not a Windows-based recovery method.
- Release still requires the same manually verified external state, original review ticket and exact local typed attestation. There is no voice unlock, automatic receipt issuance, replay, or background release.

## Verification and follow-up

Synthetic tests use disposable project roots with short-lived local Python processes and visible descendants; they also inject a missing procfs mount and unreadable/truncated command line fixtures. They verify veto while the process remains alive and release only once it exits; the command-line diagnostic never clears the marker.

A full review of live VENTUNO services/descendants, real native STT persistent-worker process containment, power-fail durability of actual eMMC storage, permission separation and post-release external effects still requires explicit physical authorization and presence. No source-only test claims to satisfy those requirements.
