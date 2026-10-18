# MyAI – source snapshot / manifest: hardlink-boundary review (2026-10-18)

**Base:** DRAFT PR #320, exact commit `13e16b6705436d695f6724abc50ab4dbd5ebf055`. Only GitHub source/test changes; the ARM64 validation must use an isolated hosted runner. No active MyAI promotion/rollback, production-board mutation or merge to main.

## Pass 1 – logic and security finding

`core/selfdev_workspace.py` already traverses source and staging directories with `O_DIRECTORY|O_NOFOLLOW`, and rejects symlink and special-file attacks. However, `_stage_source_files` accepted **any** regular inode regardless of `st_nlink`, and `_hash_pinned_regular_file` did the same for manifest creation and baseline drift checks. A hardlink under an allowlisted project path (`core/exfil.py`, for instance) can point at the *same inode* as a file outside the project. Such a file passes allowlist and symlink checks, causing source bytes to be copied to a selfdev workspace or included in a hash. `O_NOFOLLOW` does not prevent this. Creating another hardlink during an open-file read was also not explicitly checked on read completion.

## Pass 2 – changes and regression tests

- `_stage_source_files` now requires exactly one hardlink on the opened source inode **before copying** and on `fstat` after all bytes have been read. Unsupported inode link counts fail closed before new staged bytes are created, or before a session record is published.
- `_hash_pinned_regular_file` now requires `st_nlink == 1` both before and after hashing. The shared pinned-FD helper covers `build_manifest`, baseline source drift, and other users of the helper without duplicating path-based preflights.
- Existing stable size/dev/ino/mtime/ctime checks and source allowlist, directory FD traversal, executable-bit copying, and manifest semantics are preserved.
- Five synthetic regression tests: an outside secret hardlinked to an allowlisted source is rejected before staging; a hardlinked staging candidate is rejected before manifest hashing; a new hardlink to an active source is reported as drift; new hardlinks created during manifest hashing and during staging are detected after the read. None of the tests invokes real promotion or changes installed source.

## Residual risks / release NO-GO

- A local privileged process with the same UID or directory write access can modify an inode in-place; metadata checks detect many such races but not every possible noncooperating writer pattern (for example, coordinated modifications and restored metadata). Strong filesystem ownership/process-user isolation and independent signed provenance are still required.
- A hardlink created and removed entirely between the initial and final `fstat` can escape detection; the only complete policy boundary is restricting which identities may create links or modify allowlisted source trees.
- Session approval provenance, actual sandbox execution, source-to-installation promotion and rollback still require broader end-to-end integrity testing. Complete repo file review, dependency/SBOM/license audit, actual ARM64 hardware, NPU/voice and power-loss recovery gates remain open.
- Keep PR DRAFT. Do not merge to main, alter live VENTUNO services, or run a live selfdev update.

**Verification:** all source-only ARM64 tests on the exact final HEAD and inspect CI job logs; no “green” claim before that.
