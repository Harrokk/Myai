# MyAI checkpoint — transactional memory & crash recovery (2026-10-14)

## Source of truth
- Base: dev/selfdev-staging-symlink-20261014, checkpoint commit edaafa8d49d5c29b8d45196795d0ed5b796ea4c2.
- PR #122, branch dev/memory-atomic-review-20261014, commit 1ed4f12419f1cb8dfe8e44ae91e33151a204cce6: https://github.com/Harrokk/Myai/pull/122
- PR #123, branch dev/selfdev-crash-journal-20261014, commit 1942235ed97d57fb62bd6136ac7f1b988f22cb33: https://github.com/Harrokk/Myai/pull/123
- Both are DRAFT and stacked. Nothing is merged to main or deployed to live MyAI. Active VENTUNO profile selfdev promotion remains disabled.

## Issue and fix 1: memory database
1. `MemoryStore.save_if_new` previously ran SELECT in one SQLite connection and INSERT in another; multiple concurrent writers could both insert the same active memory. Replaced with a single `BEGIN IMMEDIATE` SQLite transaction covering both operations and preserving existing case-insensitive duplicate rules.
2. `MemoryStore.approve_review` and `replace_from_review` previously interpreted corrupt conflicts_json as an empty list, and replacement accepted a target even when the original list was actually empty. Now malformed or non-list metadata fails closed and replacement requires the requested target to be an explicitly recorded positive integer conflict ID.
3. New tests: eight-concurrent-writer barrier, malformed review approval, invalid or empty conflict replacement rejection, verified legitimate replacement.
4. Full VENTUNO Q temp-checkout GitHub CI: https://github.com/Harrokk/Myai/actions/runs/38528322368 — **1522 passed, 6 skipped**.

## Issue and fix 2: selfdev promotion interrupted mid-update
1. Before any active file is overwritten, record backups and planned SHA-256 hashes in `rollbacks/<promotion-id>/promotion.json` with `state: prepared`. Journal is created with a unique temporary file, flushed/fsynced and atomically replaced; parent directory fsync on platforms supporting it.
2. On success, atomically publish `state: completed` and after-hashes. On ordinary errors, rollback changed paths and record `state: reverted` if rollback succeeds. Unexpected process interruption leaves `prepared` for forensic/manual recovery.
3. A new `promote` on the same session refuses to proceed if an incomplete, missing, corrupt, or unknown journal is encountered.
4. `recover_interrupted(id, "RECOVER <session> <id>")` is an explicit, audited API. It checks all paths, backups and existing content before changing anything, refuses unknown user modifications/corrupt backups, restores only planned-version files and removes added files, then records `state: recovered`. It is not invoked automatically.
5. Old `rollback` refuses `prepared` journals, verifies backup hashes before overwriting, and rejects dangling symlinks in project paths.
6. Tests: interrupt first or second copy (synthetic `SystemExit`), full application but interrupted before final journal write, user-modified source conflict, corrupted backup rejection, manual approval phrase enforcement, incomplete rollback bypass denied, idempotent no-second-recovery, normal successful promote/rollback preserved.
7. Full VENTUNO Q temp-checkout CI: https://github.com/Harrokk/Myai/actions/runs/38529194798 — **1530 passed, 6 skipped**.

## Test context
- CI runs in a temporary checkout using a self-hosted VENTUNO ARM64 GitHub Actions runner; it does not change the live MyAI installation or its services.
- Six optional host-only ONNX/NumPy tests skipped on ARM64 were verified in separate 22/22 passing GitHub-hosted x86 run: https://github.com/Harrokk/Myai/actions/runs/38520039444.
- Prior draft PR chain: #112 camera explicit-negation handling; #113 full-tree static audit; #114 BLE RSSI safety; #115 voice and memory sensitive data; #116 GenieX watchdog; #119 file-workspace symlink protections; #120 selfdev staging symlink protections.

## Remaining work / safety constraints
- Current selfdev crash recovery is designed around one promotion **session**. It does not enforce a global lock across *all* sessions or prevent arbitrary concurrent writers modifying the same tree in the interval between SHA validation and replacement. Before unattended deployment, assess global transaction locks, directory-fd / no-follow semantics, persistence on sudden power loss and multi-session conflicts.
- The timestamp/checkpoint tests simulate `SystemExit` and I/O exceptions; no physical power-cut or 72-hour hardware reliability test was done.
- Memory conflict similarity remains heuristic and potentially ambiguous. The `enqueue_review` concurrent duplicate check still merits a dedicated atomicity review.
- History-cache cleanup GitHub Support blocker is still open per PR #110. No merge to main or disclosure of historical SHA.
- No mic, speaker, Bluetooth pairing, camera, STM32, actual ONNX/NPU hardware test, live AI service, user Windows machine, or Arduino App Lab terminal was used. The user postponed Windows App Lab network investigation.
- Do not claim all bugs or race conditions are eliminated based solely on test passing. Proceed in another draft branch after inspecting prior PR dependencies, and do not enable live selfdev promotion without further review and explicit authorization.
