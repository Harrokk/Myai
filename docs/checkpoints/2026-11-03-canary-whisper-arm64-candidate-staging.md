# MyAI: independent Canary / Whisper ARM64 candidate staging — 2026-11-03

**Status: DRAFT, source-only, config default OFF, runtime activation BLOCKED.**
No VENTUNO commands, installs, model downloads, NPU operations, microphone
tests, live speech inference, GenieX execution or tool invocations.

## Stack

- Parent DRAFT PR #377 at commit
  `495c71007a8600c87aa4de6bda7caccd2921d1e6`.
- Branch `dev/voice-canary-whisper-attestation-20261103`.
- This is a staging contract, not a claim that three independent STT models
  have run together on ARM64 or that model WER is reproduced.

## Reviewed candidate profiles

1. **Canary 1B v2, Q8_0**, Swedish-capable, GGUF file
   `canary-1b-v2-Q8_0.gguf` with a pinned `transcribe-cli` from
   handy-computer/transcribe.cpp.
   Official model notes:
   https://github.com/handy-computer/transcribe.cpp/blob/main/docs/models/canary-1b-v2.md
   Canary is batch/nonstreaming; 16 kHz mono WAV with explicit Swedish hint.
   Approximate model weight download size 1.14 GB (not measured peak RAM).

2. **Whisper large-v3 Turbo**, multilingual ggml model
   `ggml-large-v3-turbo.bin` with an independently pinned `whisper-cli`
   from ggml-org/whisper.cpp.
   https://github.com/ggml-org/whisper.cpp
   The documented CLI consumes audio files including WAV, and a later
   audited PCM-to-native bridge is needed; no fallback to untrusted shell
   commands or temporary private PCM in persistent storage is authorized.

The two candidate runtimes are **different native engines**, but their
decoding errors and OS dependencies can still be correlated. Verified model
families do not establish an authenticated human speaker.

## New guarded source modules

- `core/voice_candidate_preflight.py`: exact allowlisted profile names,
  expected filenames, external/operator-pinned SHA256 model and native binary
  hashes; check per-file contents with the existing no-symlink/hardlink and
  read-only verifier. Reject x86/armv7/RISC-V ELF headers, missing executable
  bit, setuid/setgid and malformed binaries. Never execute the binary.
- A returned `VerifiedCandidateProfile` is immutable, read-only and has no
  `transcribe()`. Thus a successful preflight alone cannot be credited as
  a valid STT vote or used as a direct new voice provider.
- `verify_independent_candidates` requires BOTH distinct candidate families;
  no partial candidate set may be presented as complete.
- `core/voice_tier_resource_budget.py`: non-authorizing estimate requiring
  **measured**, not invented, peak RSS for Parakeet/Canary/Whisper,
  additional GenieX needs, observed MemAvailable and explicit headroom.
  Sequential operation additionally needs separately confirmed worker cleanup.
  All figures in the unit tests are *synthetic test fixtures*, never VENTUNO
  measurements.

## Implementation/production NO-GO

- CLI flags, WAV/PCM exchange and bounded transcript parsing have NOT been
  implemented for either candidate. Do not pretend a header-verified ELF file
  proves that the model runs on Ubuntu 24.04 / Qualcomm QCS8275.
- ELF header verification does NOT guarantee ARM64 compatibility, dependency
  safety or binary provenance. A reviewed source commit/build and a pinned,
  audited dynamic-library dependency graph are required.
- The exact SHA256s for reviewed model and binary artifacts have not been
  obtained from releases, so none are hard-coded here. Fixture SHA values
  were calculated from tiny synthetic files in disposable hosted CI.
- Current `TrustedSTTBindings` requires an actual registered provider object,
  fully verified model bundle, and evidence from a real request. The new
  candidate profiles intentionally cannot supply that evidence yet.
- No real resource/latency/temperature measurement or concurrent trio trial.
  RAM/CPU headroom planning must not use rough internet numbers as if measured.
- Separate critical-command approval is not implemented; critical voice tool
  execution remains denied even if three STT transcripts agree.
- `voice.risk_tiered_verification_enabled` remains false and
  `config_validation.py` rejects explicit activation. No edits to the
  production factory, VENTUNO profile or operating services.

## Next safe development order

1. Review exact upstream CLI source/ABI and binary dependency graph for the
   pinned native revisions, then design private **RAM-only WAV delivery**,
   output parser and owned process group cleanup.
2. Introduce bounded native process adapters in a separate opt-in DRAFT
   with end-to-end negative tests for timeout, IPC, wrong model paths,
   language mismatch and sanitizer failures.
3. Hosted ARM64 run with real, reviewed model artifacts if policy permits,
   using isolated runner and no private recordings; measure WER on
   Swedish public fixtures, RSS, wall-clock and idle RAM.
4. Verify simultaneous/serial STT resource handoff alongside GenieX; maintain
   separate source review, explicit critical command approval and operator
   consent before any VENTUNO pilot.

**Do not merge or activate this DRAFT based on synthetic tests alone.**
