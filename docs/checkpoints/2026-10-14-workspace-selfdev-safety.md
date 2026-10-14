# MyAI – unattended workspace and selfdev safety follow-up
Date: 2026-10-14
Platform: Arduino VENTUNO Q / Qualcomm Dragonwing, ARM64, isolated GitHub runner
Current branch: dev/selfdev-staging-symlink-20261014

## Confirmed issue: General file workspace
A predictable `note.txt.tmp` written by `Path.write_text` could be precreated as a symlink and redirect writes outside the configured file workspace. Workspace listing could also reveal metadata for final-component symlinks pointing outside the workspace.

Fix: unique exclusive `tempfile.mkstemp` in same directory, flush and fsync, atomic replace, cleanup on failure; omit symlinks from workspace listing and require resolved targets under workspace root.

Tests: pre-existing symlink cannot alter outside file; listing ignores external symlink; failed atomic replace leaves original file unmodified. Updated an existing synthetic disk-full test to intercept `mkstemp` instead of the retired `Path.write_text` implementation.

Draft PR #119: https://github.com/Harrokk/Myai/pull/119
Verified ARM64 full suite: https://github.com/Harrokk/Myai/actions/runs/38527226804 – **1515 passed, 6 skipped**.

## Confirmed issue: Selfdev staging
`SelfDevWorkspace._candidate_path` used `candidate.exists() and candidate.is_symlink()`. `exists()` is false for a dangling symlink; so a staging write might create a file outside the staging sandbox. A target swap between validation and writing was also a risk.

Fix: reject symbolic links independent of target existence, stage writes in unique exclusive temporary file, recheck destination, atomically replace (leaf symlinks not followed), cleanup after failed writes.

Tests: dangling symlink cannot create outside file; simulated symlink swap cannot overwrite outside file; failure in atomic replace preserves original and removes temporary file.

Draft PR #120: https://github.com/Harrokk/Myai/pull/120
Verified ARM64 full suite: https://github.com/Harrokk/Myai/actions/runs/38527395968 – **1518 passed, 6 skipped**.

## Existing baseline
Six optional host-only ONNX/NumPy checks skip on VENTUNO ARM64 by design, but were verified with 22 passed on GitHub-hosted x86 Linux: https://github.com/Harrokk/Myai/actions/runs/38520039444.
Previous security PRs are #112 camera negation, #113 source audit, #114 BLE signal safety, #115 voice + memory safety, #116 GenieX health state safety. Drafts are stacked; no merge to main or production install.

## Outstanding analysis and boundaries
- Real-world local file directory symlink races still warrant a more thorough dir-fd / no-follow design review when enabling concurrent untrusted processes; current fixes close the demonstrated leaf-symlink and predictable-temp vulnerabilities but do not prove all TOCTOU races are absent.
- Interrupted promotion of multiple selfdev code files requires a dedicated transaction-journal / recovery design before unattended self-updates may be authorized. Do not enable `selfdev.promotion_enabled` based on these tests.
- Memory lifecycle conflict detection is heuristic; review false automatic replacements and competing updates before treating the memory system as reliable.
- Physical microphone, speaker, Bluetooth, camera, GPIO/STM32, full GenieX/NPU performance, 72-hour stress test, and Windows Arduino App Lab diagnosis remain outside safe unattended code testing; Windows troubleshooting was explicitly postponed by user.
- Server-side cached history containing past user-memory records remains an unresolved main-merge blocker per PR #110. GitHub Support cache purge may be required.
- All tests ran on checked-out isolated sources. No GitHub draft PR was merged. No live MyAI/GenieX service, installed model, file workspace, user's computer, or physical device was changed.
