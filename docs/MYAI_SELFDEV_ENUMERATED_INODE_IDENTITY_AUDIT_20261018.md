# MyAI – source and workspace enumeration: inode identity across stat/open (2026-10-18)

**Base:** DRAFT PR #321, `1ae374b7eeb5075d976e6822ca4e10f8975c8812`, verified in isolated hosted ARM64 source-only CI. No merge to main, active VENTUNO mutation, live promotion or rollback.

## Pass 1: reviewed logic and security finding

`_stage_source_files` and `build_manifest` enumerate filenames through directory FDs, verify each entry's type using `os.stat(name, dir_fd=..., follow_symlinks=False)`, then reopen the entry using `os.open(name, O_NOFOLLOW, dir_fd=...)`. `O_NOFOLLOW` is sufficient to stop a symlink substitution, but **not** replacement by another valid regular file or directory with the same basename. The read can therefore use a different inode from the one whose type/allowlist path was validated. In staging this could admit bytes of a moved sensitive file and persist them in a new workspace. Manifest hashing could similarly attest a substituted inode rather than the enumerated one. The previously added hardlink and during-read stability checks alone do not close that pre-open window.

## Pass 2: change and regression tests

- New `_require_enumerated_inode(listed, opened_fd)` obtains `os.fstat` for the actually opened descriptor and compares `st_dev`, `st_ino`, and file type (mode `S_IFMT`) with the original no-follow enumeration `stat`. Any change fails closed, without reading the new file/directory's contents.
- Call it immediately after opening source directories and source regular files, before target directory/file creation or any source byte copying.
- Call it immediately after opening manifest child directories and manifest source files, before traversing/hash computation.
- Preserve per-file nlink==1, stable size/mtime/ctime hashing, no-follow parent traversal, allowlist semantics, and explicit rejection of unsafe special files.
- Four synthetic regression tests substitute different **regular** single-link inodes of the same filesystem between `stat` and `open`: staging source file, manifest file, staging directory, manifest directory. These intentionally bypass symlink-only defenses and assert no substituted source is staged or hashed.

## Residual security constraints and release NO-GO

- Passing the inode comparison does not lock a mutable source file or prevent a privileged concurrent writer after the check. Our stable-metadata read checks are best-effort detection, not a kernel-enforced immutable snapshot.
- The workspace and project directory ownership isolation model must be validated against actual deployment; same-UID writers can still move directory aliases after FD opening, block access, or mutate bytes in-place.
- Full source file review across the 900+ tracked repository entries, third-party dependency and SBOM/license audit, vendor ABI/device firmware review, and physical NPU/audio/power-failure recovery testing are not complete. This PR is DRAFT and must remain NO-GO for main and active VENTUNO.
- Requires full *isolated hosted ARM64 source-only* CI on the exact final commit, with job logs inspected before reporting green.
