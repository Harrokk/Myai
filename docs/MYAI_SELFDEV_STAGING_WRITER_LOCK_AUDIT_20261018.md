# MyAI selfdev staging write / verification lock audit (2026-10-18)

**Base:** DRAFT PR #325, exact commit `462d49037456a663c7c5a0a056840312d1e495ec`. Source only. No production self-modification, hardware access or merge.

## Pass 1 – confirmed concurrent cooperative writer gap

PR #319 serialized `SelfDevVerifier.verify()` with promotion/rollback using the private OS-level `.promotion.lock`. But `SelfDevWorkspace.write_text()` did not acquire that lock. It could edit a staged candidate while another instance held a verifier or promotion lock; the verification previously relied on post-run manifest checks to detect a changed candidate. A writer could also change the staged file before invalidating `verification.json`, leaving a time window where old passing metadata survived the edit.

Source pinning and post-run digest comparisons remain important, but a project API editing files should itself cooperate with the shared project lock.

## Pass 2 – narrow fix

- Wrap `write_text()` in the existing `_project_mutation_lock_for_workspace` (no new lock name or lock ordering). This enforces mutual exclusion with `verify()`, promotion, rollback and other cooperating writers.
- Validate the requested candidate under the lock, revoke any previous verification **before the first staged mutation**, then perform the existing dirfd-pinned atomic file writer in a private helper.
- A lock collision fails before approval invalidation and before writing. An invalidation error fails before modification, preserving the old candidate and allowing the operator to inspect the existing approval as **stale / non-release-authorizing**, not silently promoting it.
- Add regression tests for lock conflict, failed approval invalidation and approval revocation before the destination rename.

## Limitations / release NO-GO

POSIX `flock` remains **advisory**: a process running as the same UID can bypass the project API and directly edit or replace inodes in the writable session directory. No new cryptographic sandbox provenance or distinct service UID is provided. Other on-device GitHub Actions runner processes need privilege isolation; hash/ctime checks are not an atomic filesystem snapshot against a privileged writer.

Full dependency graph/SBOM/license/ABI, actual Bubblewrap/NPU/audio, crash/power-loss recovery and historic workflow source baseline review remain release blockers. Require exact-HEAD hosted ARM64 tests. **DRAFT only: no main merge, deployment or live promotion.**
