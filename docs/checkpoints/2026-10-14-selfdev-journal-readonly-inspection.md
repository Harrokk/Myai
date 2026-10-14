# MyAI checkpoint — säker journalläsning och skrivskyddad återställningskontroll
Date: 2026-10-14
Current branch: `dev/selfdev-recovery-readonly-check-20261014`
Main baseline: draft PR #128 and PR #127.
No installation, merge, live service restart, physical test or user file mutation.

## Verified PR #129 — key publishing and strict journal reads
URL: https://github.com/Harrokk/Myai/pull/129
Branch: dev/selfdev-journal-read-safety-20261014
Verified commit: 4e582c8a295a84d2cd4281fca2f566fa159ae415
Run: https://github.com/Harrokk/Myai/actions/runs/38539767068 — 1569 passed, 6 skipped.

- Local private integrity key is fully written/fsynced in a temporary inode before exclusive os.link publication. Temporary file is removed; directory fsynced. Existing invalid private key is not regenerated or silently replaced. This reduces the incomplete-key publication risk but cannot protect against same-UID malicious code or all physical power-loss edge cases.
- Signed journal readers now use no-follow file descriptor where supported, bounded 1 MiB read, regular-inode / single-link check and strict JSON. Reject nonfinite numeric constants, duplicate object keys, huge files, hardlinks and symlinks. Legacy source parsing and raw archival are now performed on a single, consistent byte snapshot rather than two independent file reads.
- Eight new regression tests including key creation failure cleanup.
- First CI run on intermediate changes reported one old symlink-test diagnostic mismatch; fixed without weakening no-follow enforcement, and retested to green.

## Verified PR #130 — purely read-only manual recovery inspection
URL: https://github.com/Harrokk/Myai/pull/130
Branch: dev/selfdev-recovery-readonly-check-20261014
Verified code commit: 25c086b674dae048ed2ce59b73a08f2d50ed7aa9
Run: https://github.com/Harrokk/Myai/actions/runs/38540126333 — 1575 passed, 6 skipped.

- `SelfDevPromotionManager.inspect_recovery(promotion_id)` checks an authenticated journal, linked backup integrity and original/planned hashes and returns advisory fields such as status, journal_state, file_count and would_restore. Unknown/corrupt journal and newer external code are blocked.
- It makes no writes, audit events, lock file creation, key generation, recovery or rollback. Six new tests compare project file bytes before/after inspection; all pass.
- Successful preflight status deliberately says `preflight_ok_requires_manual_approval`; it is not permission to run code promotion or bypass human consent.

## Work safety and boundaries
- On-device VENTUNO selfdev promotion remains disabled; no live MyAI, audio, camera, Bluetooth, GPS, STM32 or NPU code path was exercised. All tests used temporary GitHub runner checkout.
- Six host-only ONNX/NumPy cases are skipped in ARM64 suite by design and previously independently passed as part of 22 passing tests on GitHub hosted x86 runner https://github.com/Harrokk/Myai/actions/runs/38520039444.
- Advisory kernel locks and journal SHA checks do not eliminate outside-writer races, especially same-UID attacker or TOCTOU between final hash and rename. Project-local HMAC key likewise is not a root of trust against same-UID compromise.
- Real sudden power-cut tests on Ventuno eMMC have NOT been performed; fsync and simulated SystemExit cannot establish physical crash consistency.
- Legacy unsigned journals under PR #128 require explicit migration and external provenance verification; no auto migration.
- Cached historic sensitive memory cleanup remains main merge blocker under PR #110. GitHub draft chain #112 #113 #114 #115 #116 #119 #120 #122 #123 #124 #125 #126 #127 #128 #129 #130 still pending; none merged or deployed.
- Windows Arduino App Lab invalid board IP diagnosis remains deferred by the user.

## Suggested next isolated work
Perform adversarial privilege-boundary audit on backup paths, lock file metadata, symlinked workspace session roots; test read-only report with malformed nested JSON; inspect source target race handling, but do not promise elimination of all races. Before deployment, plan a real physical power-cut test with explicit user approval.
