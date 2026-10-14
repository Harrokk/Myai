# MyAI checkpoint — integritetskontrollerad selfdev-journal och avbruten rollback
Date: 2026-10-14
Current development branch: `dev/selfdev-journal-integrity-20261014`
Latest verified code commit: `25a8afcb2791d48d201e0391dbf03cba07eccc89`
Draft PR #127: https://github.com/Harrokk/Myai/pull/127
Base: PR #126 / `dev/selfdev-external-writer-durability-20261014`

## Findings
1. Selfdev recovery relied on editable `promotion.json` fields such as `state`, `backups`, `planned_hashes` without verifying the journal's own integrity. A state change to `completed` could mask an interrupted update from the cross-session pending gate.
2. Journal-based recovery allowed any paths under the project root through `_safe_project_target`; paths such as `runtime/secret.txt` were not restricted to selfdev source-code file allowlist. A tampered journal could try to restore or remove unintended project files.
3. Normal manual rollback wrote its final state only after restoring multiple files. If interrupted halfway, the old `completed` journal would not reliably support resuming rollback, and another session might incorrectly proceed.

## Implemented in draft
- Journal records are sealed using HMAC-SHA256. Secret key in project-local `runtime/selfdev/.journal-integrity-key` created O_CREAT|O_EXCL with private POSIX permissions, fsynced, read with no-follow where supported; fstat validates regular file, single link and private permissions. Every journal read checks version, MAC and key first. Missing, invalid, unsigned or symlinked records fail closed. All ordinary journal state updates are re-sealed.
- `_safe_project_target` and `_safe_backup_path` enforce the same `_allowed_relative_path` source allowlist as selfdev staging.
- Rollback first writes an authenticated `rollback_prepared` journal. An interruption can be recovered explicitly using `RECOVER <session> <promotion_id>`, continuing from a mix of originals and planned code; completion is sealed as `recovered`. New promotions remain blocked by pending journals across sessions.
- No automatic recovery and no promotion-enablement change.

## Verification
- Full real VENTUNO ARM64 Actions runner temporary checkout, https://github.com/Harrokk/Myai/actions/runs/38536458694 — **1554 passed, 6 skipped**, source compile successful.
- Previous branch PR #126: 1545 passed, 6 skipped.
- Nine new targeted tests: changed planned hashes, forged completed state, deleted integrity key, signed forbidden runtime path, valid sealed promote+rollback, symlinked journal, power-loss simulation midway rollback, loss after restore but before acknowledgment, and a pending rollback blocking a second session.
- Six optional ONNX/NumPy-host-only tests skipped on ARM64 previously passed in GitHub-hosted x86 run https://github.com/Harrokk/Myai/actions/runs/38520039444 (22 pass).

## Security boundaries and migration blocker
- The secret key belongs to the same local project/account as selfdev; same-UID malware with access to both key and journal can forge the HMAC. This protects against journal-only alteration and corruption, NOT a fully compromised same-UID process. Additional privilege isolation and secure key management would be required to withstand that adversary.
- **Breaking format change:** legacy unsigned `promotion.json` journals, even legitimately completed ones, now fail closed. Before any merge/deployment, design a reviewed migration for legacy records or explicitly verify none exist in the target environment. Do not silently strip this validation or auto-accept unsigned historical journals.
- Simulated exceptions and fsync operations are not equivalent to a real sudden power loss to Ventuno eMMC; advisory locks and noncooperating-writer TOCTOU still remain.
- GitHub Support history/cached sensitive-memory purge blocker from PR #110 remains; earlier draft PR chain #112, #113, #114, #115, #116, #119, #120, #122, #123, #124, #125, #126 still pending. No merge into main and no production install.
- Windows Arduino App Lab IP issue postponed at user request. No on-device microphone, speaker, BLE, GPS, camera, STM32, NPU or live code promotion operations performed.

## Suggested next unattended work
Review old-journal migration and integrity key storage/privilege boundaries. Add adversarial metadata tests for malformed or extra fields, symlinked/hardlinked backup files, partial recovery interrupted multiple times, and proof that no destructive operation is allowed without explicit authorized action. Do not enable unattended source promotion.
