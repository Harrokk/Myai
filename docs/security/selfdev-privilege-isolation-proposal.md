# MyAI privilege-isolation architecture — non-deployment proposal

**Date:** 2026-10-14
**Status:** Design for review only. No installation, account creation, service restart, credential rotation, systemd modification or promotion authorization.

## Security problem

Selfdev currently runs under the same Unix identity as some MyAI runtime processes in the tested layout. A project-local `.journal-integrity-key`, `.promotion.lock` and HMAC-protected `promotion.json` can detect accidental corruption, symlinks and writers with *different* accounts. They cannot provide a security boundary against arbitrary malicious code running under the **same UID**, because that code could read or replace both the signing key and records, ignore advisory locks, or overwrite source bytes before/after SHA-256 checks. POSIX directory-fd anchoring fixes parent redirection but not malicious privileged leaf replacement under a writable directory.

## Proposed future boundary (NOT implemented)

1. **Runtime service identity**: launch dialogue, memory and tool-selection services under a limited `myai-runtime` identity. Source code and release directories are readable but not writable. The runtime must not have access to the journal signing key, writable backup directories, or privileged update IPC. Secrets for other services need separate minimal permissions. No camera/mic/BLE privileges should be broadened for selfdev.
2. **Updater service identity**: a separate `myai-updater` identity owns code staging, a private signing key, backup/journal records and the release transaction lock. The updater does not directly accept arbitrary filesystem paths or Python code strings from the runtime.
3. **Typed, validated request protocol**: runtime may submit a bounded request with a candidate revision identifier, file manifest hashes and an intent-specific human-approval reference. The updater independently validates allowlisted destinations, signed build artifacts, exact manifest bytes, source provenance, worktree state, configuration flags and the approval reference. It rejects unknown path types, symlink/hardlink escapes, incomplete legacy recovery and unsigned release artifacts.
4. **Staged releases**: build all files in a versioned, private temporary directory on the same filesystem, fsync files and directories, verify as a whole, then atomically publish a release directory. Changing an active release pointer and restarting services would be **explicitly gated**, ideally during a maintenance operation with a rollbackable previous release. Do not hot-swap multiple active Python source files individually.
5. **Independent journal key**: key readable only to updater identity, with owner-only parent directories. Either a kernel-controlled protected secret or root-provisioned file, with a carefully audited rotation/recovery design. A root/admin user can still override protections and physical-storage durability remains separate.
6. **Least privilege and audit**: failure of mandatory audit logging must block any privileged mutation. Audit store should be owned by a privileged service not writable by the runtime account. Cross-process locking and pinned directory descriptors remain additional safeguards, not the sole authorization boundary.
7. **Recovery and legacy migration**: support read-only preflight under lower privileges; actual recovery and migration require explicit human authorization, physical deployment migration planning and backed-up integrity checks. Never auto-sign previously unsigned interrupted journal records.
8. **No silent enabling**: leave `selfdev.enabled`, `promotion_enabled`, camera, microphone, location, terminal write, restart and auto-execution feature flags disabled in production until separately authorized.

## Offline verification plan (safe without physical access)

- Unit-test protocol validation using two simulated roles, malicious request paths, wrong signature/manifest, stale approval, duplicate requests, damaged record, lost signature key, changed source inode, and many concurrent workers.
- Test all state transitions on temporary directories and disposable SQLite stores. Build a clean x86/Linux and ARM64 source-only CI matrix; preserve the Windows fallback subset tests separately.
- Where a dedicated disposable Linux container is available, integration-test two actual Unix UIDs, verifying that the runtime cannot read key or write code, while the updater can. **Do not use host account changes or elevated actions on a shared VENTUNO runner.**
- Produce a permission matrix for every directory and key, with independent review. Static source audit should reject production configs that enable automatic mutation before migration approval.
- Record crash test limits honestly: simulated `SystemExit` and fsync success are not power-loss guarantees.

## Cannot be settled by repository-only tests

- Actual user/group/systemd changes on Ventuno and compatibility with the current installed runtime; needs physical or explicitly authorized on-device deployment.
- Sudden eMMC power loss, real filesystem/cache persistence, journal order after reboot and resilience of audio/voice/USB devices after restart.
- GitHub server-side removal of cached dangling objects and previous sensitive history references, still gated by GitHub Support [PR #110](https://github.com/Harrokk/Myai/pull/110).
- Arduino App Lab Windows invalid-board-IP investigation is separately postponed.

**Release criterion:** only a reviewed multi-identity implementation with successful isolated tests, an approved migration and physical fault-testing plan should be considered for installation. This document is not that approval.
