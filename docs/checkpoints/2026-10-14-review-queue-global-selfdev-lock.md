# MyAI – atomisk granskningskö och låsning över selfdev-sessioner
Date: 2026-10-14
Branch: dev/selfdev-global-lock-20261014
Deployment status: draft code only, NOT merged or installed.

## Verified developments

### Pending memory review race & conflict escalation
- PR #124: https://github.com/Harrokk/Myai/pull/124
- Commit: 88edf246ad3f83ddc0916a056890a5ca33d20e15
- `MemoryStore.enqueue_review` now uses SQLite `BEGIN IMMEDIATE` before SELECT/INSERT to prevent concurrent duplicate pending reviews.
- New conflict IDs discovered for an existing pending candidate are merged under the lock instead of being silently discarded, so a later discovered conflict prevents ordinary approval.
- Existing malformed conflict metadata aborts rather than automatically assuming there are no conflicts.
- Tests for 8 concurrent requesters, concurrent conflict union, conflict escalation, and malformed metadata.
- Full isolated VENTUNO ARM64 CI: https://github.com/Harrokk/Myai/actions/runs/38532821132 — **1534 passed, 6 skipped**.

### Project-wide locking for code promotion, rollback and recovery
- PR #125: https://github.com/Harrokk/Myai/pull/125
- Commit: 1426e22e9cf5fe50879c2351e0f9f7410658d1d9
- Project-shared advisory OS lock in `runtime/selfdev/.promotion.lock` (POSIX `fcntl.flock`, fallback `msvcrt` byte locking for Windows development, unsupported platforms fail closed). Lock protects `promote`, `rollback` and `recover_interrupted` from cooperating MyAI sessions with nonblocking contention failure.
- After a process exception or synthetic `SystemExit`, operating system lock is released, but the prepared crash journal prevents another session from promoting over unfinished code.
- New-promote prerequisite scans known session directories for unfinished/missing/corrupt journals; no longer limits scan only to the calling session.
- Four tests: concurrent promotion denial, rollback lock contention, synthetic interruption release + journal gate across sessions, recovery lock contention.
- Full isolated VENTUNO ARM64 CI: https://github.com/Harrokk/Myai/actions/runs/38533180677 — **1538 passed, 6 skipped**.

### Optional host-only tests
- Six ONNX/NumPy optional cases skip on ARM64 runner; all previously verified through separate 22-passing test suite on GitHub-hosted x86 Linux: https://github.com/Harrokk/Myai/actions/runs/38520039444.

## Draft PR dependency chain
#112 camera intent; #113 full-tree static audit; #114 BLE RSSI fail closed; #115 voice and sensitive memory; #116 health watchdog; #119 workspace safe writes; #120 selfdev staged symlink protection; #122 memory atomic review metadata; #123 manual selfdev crash journal recovery; #124 atomic pending review queue; #125 multi-session promotion lock. All pending review. Main and live VENTUNO installation unchanged.

## Remaining work
- Kernel file locks are advisory. Non-cooperating filesystem writers can still race with MyAI source changes; path validation and filesystem behavior still require hardening before enabling unattended updates.
- Cross-session pending journals block new promotion, but multiple simultaneously pending historical journals, arbitrary external selfdev roots, and rollback interactions merit further review.
- Simulated SystemExit tests are not physical power-cut durability verification. There is no proof of safe code hot-swap, service restart or long-term stability. Do not enable selfdev promotion by default.
- GitHub Support cached historic SQLite records cleanup under PR #110 remains separate merge blocker.
- User postponed Windows Arduino App Lab invalid IP/mDNS investigation. No microphone, USB audio, BLE pairing, camera, NPU, STM32, or live service operations executed here.
