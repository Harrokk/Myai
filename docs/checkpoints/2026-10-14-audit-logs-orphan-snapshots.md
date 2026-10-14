# MyAI checkpoint — säker revisionslogg och skrivskyddad inventering av återställningsfiler
Date: 2026-10-14
Latest development branch: `dev/selfdev-orphan-snapshot-inspection-20261014`
Latest verified code commit: `82e4cf42e5b0bada9e11463c71cf331cd29fa8f8`
All changes are draft PRs and are NOT merged into main or deployed to live VENTUNO MyAI.
Production selfdev promotion remains disabled.

## Draft PR #133 — safer audit/JSONL file handling
https://github.com/Harrokk/Myai/pull/133
Base branch: `dev/selfdev-backup-snapshot-20261014`
Branch: `dev/audit-log-no-follow-20261014`
Verified code commit: `71f59e06688e1807ba350bf4e453f4ecba384be8`
CI: https://github.com/Harrokk/Myai/actions/runs/38545672736 — **1590 passed, 6 skipped**.

Finding: `core/jsonl_log.py` used ordinary `Path.open("a")`, following symlinked final destinations, including configured required `runtime/audit.jsonl`; log rotation and `read_recent_audit` also trusted symlinked entries.
Fix: safe parent-component checks, os.open with O_NOFOLLOW/O_NONBLOCK where supported, fstat regular single-link inode validation, owner and group/other writable checks on POSIX, 0600 new logs; prevalidate all rotated destination entries before renaming/deleting; read audit log from fd with the same inode checks. Seven regression tests include redirect to unrelated file, dangling symlink, rotation slot symlink, hardlink, symlinked parent, mandatory audit fail-closed behavior and refusal to read outside logs.
One existing selfdev symlink test expectation was updated: the newly required audit check now correctly blocks the attempted promotion BEFORE reaching the later selfdev symlink check. Original source remains unchanged.
Limitations: non-cooperating same-user process may still swap a parent directory after lexical check; kernel directory-descriptor-relative operations and permission isolation would be required for stronger protection. Generic JSONL code may be used elsewhere: review compatibility before merge.

## Draft PR #134 — non-destructive leftover snapshot inspection
https://github.com/Harrokk/Myai/pull/134
Branch: `dev/selfdev-orphan-snapshot-inspection-20261014`
Verified code commit: `82e4cf42e5b0bada9e11463c71cf331cd29fa8f8`
CI: https://github.com/Harrokk/Myai/actions/runs/38546034056 — **1594 passed, 6 skipped**.

Finding: `_backup_verified_snapshot()` creates `.verified-backup-*.tmp` files; normal exceptions clean up but SIGKILL/physical power loss can leave them in private backup trees.
Fix: new `SelfDevPromotionManager.inspect_recovery_artifacts(promotion_id)` is read-only, never generates key/lock, never removes files or reads their contents, never invokes recover/rollback. Recurses backup tree without intentionally following symlinks, caps traversal at 5,000 entries, blocks on symlinked directory or file, reports approximate orphan snapshot count and whether review is needed. Four tests cover untouched source/backup bytes, detection, no missing-path file creation, unsafe file and directory symlinks.
Limitations: a reported temp filename is NOT evidence that deletion is safe; no deletion or automatic cleanup was implemented. Non-cooperating same-UID directory races remain.

## Tests
- All full-suite tests executed on temporary GitHub Actions checkout on self-hosted VENTUNO Q ARM64 runner, not live MyAI /home/arduino installation.
- Six optional host-only ONNX/NumPy cases skipped on ARM64 are separately verified on GitHub-hosted x86 (22 passed): https://github.com/Harrokk/Myai/actions/runs/38520039444.
- No physical eMMC power loss, BLE, audio recording, camera, NPU or STM32 tests were performed, no active service changes or selfdev promotion.
- Cached historic sensitive-memory GitHub Support cleanup from PR #110 still blocks planned main merge. Stacked draft PRs #112 #113 #114 #115 #116 #119 #120 #122 #123 #124 #125 #126 #127 #128 #129 #130 #131 #132 #133 #134 await review.
- Windows/Arduino App Lab invalid board IP access troubleshooting was postponed by user.

## Next recommended safe development
1. Audit inherited path-safety limitations in audit JSONL rotation, especially races with uncooperative writers. Consider descriptor-relative openat and OS user separation only in isolated tests.
2. Inspect project files for unsafe symlinks and hardlinks without accessing user data; ensure source promotion uses fail-closed audit before changes.
3. Review PR stack and GitHub Support purge blocker before any merge; do not auto-enable selfdev or assume test suite proves power loss resilience.
