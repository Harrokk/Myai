# MyAI: RAM-only candidate WAV handoff checkpoint — 2026-11-03

Status: **DRAFT / GitHub-hosted source-only**. Base is PR #378 (commit
`42e3c826c43b03712570c010dda3bffda255b11b`). Branch
`dev/voice-candidate-ram-wav-20261103`.

## Motivation

Canary via transcribe.cpp and Whisper via whisper.cpp accept 16-kHz mono
WAV audio. MyAI currently processes bounded raw 16-bit PCM, and writing
actual user audio to a normal disk-backed temporary WAV would create an
unnecessary private-data retention risk.

## Source-only helper

- `core/voice_candidate_audio_memfd.py` converts only bounded
  **16,000 Hz, 1-channel, 16-bit little-endian** PCM segments into a
  canonical 44-byte-header WAV.
- Rejects non-bytes, odd PCM length, zero bytes or >30 seconds of audio
  **before** allocating memory/file descriptors.
- Uses Linux `os.memfd_create` with `MFD_CLOEXEC | MFD_ALLOW_SEALING`.
  Requires `F_SEAL_WRITE/GROW/SHRINK/SEAL` and checks that all seals
  were applied. No fallback to normal `/tmp`, Python `tempfile`, disk
  files, persistent sample storage, arbitrary shell arguments or raw PCM
  in native process command arguments.
- Context manager yields a descriptor and `/proc/self/fd/N` path for
  **future** explicit `pass_fds=(N,)` only, then closes the descriptor
  even on failure. It does not spawn any real native CLI.
- Disposable hosted ARM64 tests validate standard WAV headers, 16kHz
  samples, sealed immutability, CLOEXEC inheritance rules, explicit
  passing to a synthetic Python-only test child, bounds and private
  error redaction.

## Still unsafe / unsupported until independently reviewed

- Native Canary/Whisper CLI compatibility with a `/proc/self/fd/N`
  pathname remains **untested**. Some WAV readers require a filename
  suffix, seekable regular file, or other path semantics.
- Linux memfd is RAM-backed, but **swap** may persist memory pages if
  activated by the OS. An explicit no-swap/privacy review is needed on
  the final target.
- The future native child must be launched only from a reviewed fixed
  and pinned ARM64 binary with pinned runtime libraries, offline
  sanitized environment, owned process group, bounded stdout and
  guaranteed child cleanup.
- The PINNED model and binary preflight in PR #378 does not constitute
  a working STT provider. No voice factory registration yet.
- Resource budget, actual inference latency, Swedish command accuracy,
  GenieX handoff and memory profiling have NOT been tested on VENTUNO.
- Config flag `risk_tiered_verification_enabled` remains false and
  config validation still rejects enabling it. Critical voice tool
  actions remain blocked without a separate authorization channel.

**No installation, no physical VENTUNO commands, no models, no microphone,
no private data, no actual native inference and no production merge.**
