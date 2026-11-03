# MyAI native STT – recursive ELF dependency review (source-only checkpoint)

Date: 2026-11-03
Parent: DRAFT PR #382, commit
`9eb190880be4da846a0d73b21ee20a59b234fcac`
Branch: `dev/voice-native-transitive-elf-audit-20261103`

**No deployment, no VENTUNO commands, no model weights, no recordings,
no native speech inference, no runtime factory registration.**

## Previous verified state

- DRAFT PR #382 completed full pinned, CPU-only native AArch64 builds of
  `transcribe-cli` and `whisper-cli` from exact Git SHAs.
- MyAI hosted source suite: 4,824 passed / 10 skipped / 0 failed at that
  revision ([CI 41693607489](https://github.com/Harrokk/Myai/actions/runs/41693607489)).
- Complete hosted native build, immediate `DT_NEEDED` allowlist and
  model-free Canary WAV startup were green
  ([CI 41693607048](https://github.com/Harrokk/Myai/actions/runs/41693607048)).
- AArch64 glibc loader `ld-linux-aarch64.so.1` is permitted only when its
  SONAME matches the already approved PT_INTERP path. No wildcard loader
  exemption was added.

## New implementation

- `scripts/ci_native_cli_library_closure.py` recursively enumerates the
  `DT_NEEDED` dependency graph of both *already approved* full native
  CLI binaries and their host operating-system libraries using `readelf`.
- No `ldd`, `dlopen`, dynamic loader execution or native code execution
  is performed by the closure analyzer. It is restricted to a disposable
  GitHub-hosted aarch64 runner and known root-owned, non-writable
  `/lib`/`/usr/lib` AArch64 system directories.
- Denies an unknown transitive SONAME, wrong ELF ISA/class/endian,
  unexpected SONAME, RPATH/RUNPATH/audit hooks, duplicate direct edges,
  library path escape, missing or ambiguous host file and unexpected
  dynamic loader.
- Hashes the checked system libraries with SHA-256 after reading their
  metadata. Hashes are **observational evidence**, not externally reviewed
  signatures; another OS revision may legitimately produce different
  digests.
- `tests/test_ci_native_cli_library_closure.py` supplies synthetic
  graph/ELF tests for missing, wrong-ISA, wrong-loader, unknown,
  duplicated or injected transitive dependencies.
- The previously created `.github/workflows/native-full-cli-build.yml`
  now runs this check after the existing allowlist gate and before the
  model-free startup test, only on the two named DRAFT source branches.
  No `workflow_dispatch` has been added.

## Remaining hard release gates

1. Pinned model weights and actual Canary/Whisper inference **have not
   been run**. Real Swedish WER, negation/numbers, latency and RSS are
   unknown. Synthetic, model-free C++ tests do not establish STT quality.
2. Host dynamic-library closure is **not** library provenance on
   VENTUNO. Qualcomm Ubuntu versions, loader paths, system ABI, package
   signatures and kernel containment require a separate approved review.
3. Actual dynamic runtime loading (`dlopen`), transitive plugins,
   same-user tampering, glibc IFUNC resolution, insecure process
   boundaries and the runtime OS cannot be fully ruled out by ELF
   `DT_NEEDED` inventory alone.
4. The current STT candidates must stay disabled and unregistered in
   production. Configuration validation **rejects** enabling
   `risk_tiered_verification_enabled`.
5. Critical voice-controlled actions remain blocked without separately
   authenticated human approval; three STT models voting the same
   phrase cannot authenticate the speaker.
6. Two-pass independent code/security audit, controlled model-backed
   hosted quality/latency/resource tests, approved model manifests,
   operator consent and physical VENTUNO pilot must precede activation.

Do not merge or deploy the stack based on this staging check alone.
