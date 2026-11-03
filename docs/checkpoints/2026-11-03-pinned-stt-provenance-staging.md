# Source-only checkpoint: pinned STT provenance and dispatch revalidation

Date: 2026-11-03
Repository: Harrokk/Myai
Base: DRAFT PR #375, commit bda0e4a6579444d473b7d994d2638eb07636ede2
Branch: dev/voice-tiered-provenance-guard-20261103

**State: review-only DRAFT, feature flag remains OFF and rejected by config
validation. No VENTUNO, microphone, model download or service actions.**

## Why this checkpoint

Prior tiered STT verification accepted a caller-supplied SHA256 string as
model identity. Such a string by itself does not establish that the actual
native inference used approved model weights. This staging increment refuses
the unverified string in `TrustedSTTBindings`.

## Added / changed

- `core/voice_model_provenance.py`: audited offline per-file SHA256 checks
  against trusted manifest entries; bounded file count/size, absolute root,
  no symlinks, no hardlink aliases, no group/owner/world writable model
  files or root, file descriptor and stat consistency, generic non-sensitive
  failures. Produces a sealed `VerifiedSTTModel` with bundle fingerprint.
- `core/voice_tier_identity.py`: binds provider object and its exact
  `model_name` directory to a previously checked model bundle. Raw
  `family`/`sha256` records now fail; the provider cannot self-appoint
  a model identity. Read-only file attributes checked for every vote.
- `core/voice_tier_flow.py`: checks the registered model and bundle before
  the first and every backup transcription. Unknown or modified models block.
- `core/voice_tier_authorization.py`: rechecks model provenance right
  before allowing tool dispatch, along with existing receipt TTL, Stop,
  HMAC plan and single-use checks. Critical actions remain blocked.
- `modules/voice/sherpa_onnx_provider.py`: optional `trusted_model_file_hashes`
  map must name all four Parakeet release files and contain lowercase SHA256
  hashes; `prepare_verified_model` reads tiny metadata and hashes model
  bytes without importing native recognizer. A later _load_model call
  checks the bundle again before calling the existing native loader.
  Legacy/unpinned Parakeet behavior is unchanged and is not eligible for
  trusted tiered STT votes.
- Synthetic test fixtures are real small read-only files hashed at test
  time; not fabricated SHA strings. New negative tests cover file changes
  before/during STT, after receipt, symlinks, hardlinks, unexpected writable
  permissions, checksum mismatch and path tampering.

## Remaining blockers

1. Trusted manifests must come from separately reviewed, pinned release
   assets, **never the model directory itself or STT response text**.
2. Native loading must be isolated with bounded hard timeouts and the
   execution environment must prevent model path replacement or mutation.
   A Python file stat check is not a security boundary against an attacker
   who can write as the same user or modify executable code.
3. Factory + VoiceSession are not yet wired to construct verified bundle
   identities for actual Parakeet/Canary/Whisper models; no production
   model-family independence has been established.
4. Hard critical voice authorization remains absent. Three agreeing STT
   outputs are not speaker authentication; separate approval is required.
5. Existing VoiceSession resource handoff, Silero timing, model response
   latency, ARM64 memory budgets and noisy Swedish recognition require
   controlled host tests, then an explicitly approved physical pilot.
6. A second independent security review and CI of the exact final SHA must
   pass before any staging merge or opt-in activation.

This PR must not merge into production or change the VENTUNO voice flags.
