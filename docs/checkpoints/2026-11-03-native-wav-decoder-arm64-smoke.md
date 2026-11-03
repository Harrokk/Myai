# MyAI: actual ARM64 decoder / sealed memfd compatibility smoke

Date: 2026-11-03
Branch: `dev/voice-native-wav-decoder-smoke-20261103`
Base: DRAFT PR #380 (`9142cd4f0c97dce688da0b0c9ea7ea3e668341ed`)
Status: **DRAFT. No production activation. No VENTUNO actions.**

## What this test establishes

A disposable GitHub-hosted ARM64 worker compiles and runs two *actual*
upstream C++ **audio decoders** against MyAI's existing
`sealed_pcm16_wav_memfd` in-memory WAV container:

1. **Canary candidate decoder**: pinned transcribe.cpp commit
   `5700f127e38dd53c4735ea23ef743b4b538eacd4`,
   `examples/common/wav.cpp` and `dr_wav.h`.
2. **Whisper candidate decoder**: pinned whisper.cpp commit
   `4da27c41cebadb3cbbcd2563e9c7cbc8d84bdcad`,
   `examples/miniaudio.h` used by
   `examples/common-whisper.cpp::read_audio_data`.

The test compiles the exact upstream decoder code using native AArch64
`g++`, generates only eight samples of synthetic, silent 16 kHz mono
PCM16 audio, and hands the sealed descriptor to a C++ process at
`/proc/self/fd/N`. Both decoders must successfully read precisely eight
frames. The same child must **fail** to access the descriptor if it was
not explicitly passed through `pass_fds`. No persistent audio file or
voice data is used, and stdout/stderr from the C++ harness is suppressed.

- Workflow: `.github/workflows/native-wav-decoder-smoke.yml`.
- Checked-in C++ harness: `tests/native/candidate_wav_reader_smoke.cpp`.
- Host probe: `scripts/ci_native_wav_probe.py`.
- Completed native run:
  https://github.com/Harrokk/Myai/actions/runs/41682147510
  **SUCCESS (GitHub-hosted ARM64)**.

## Source review and production limitations

- This verifies WAV decoding using genuine upstream C++ code and fd
  inheritance semantics. It does **NOT** compile or execute either entire
  `transcribe-cli` or `whisper-cli`, load a model, transcribe speech,
  establish native runtime dependencies, or measure latency/RAM.
- Exact upstream decoder commit IDs are pinned and verified in CI.
  They have **not** been independently audited line by line for native
  security vulnerabilities.
- The decoders were compiled on GitHub's Ubuntu 24.04 ARM64 environment,
  **not** the Snapdragon/Qualcomm-specific VENTUNO Q board.
- A successful model-free decoder test does not establish support for
  all real model files, Swedish WER, cancellation under native inference,
  dynamic library provenance, secure cgroup containment, no-swap audio,
  or speaker authentication.
- The operational flow is still behind
  `voice.risk_tiered_verification_enabled=false`, with configuration
  validation rejecting attempts to activate it. Critical spoken tool
  commands are blocked until separately authenticated human approval is
  implemented.
- No VENTUNO commands, models, downloads, microphone, GenieX calls,
  services, external data, actual user audio, deployment, or merge.
- Next hard requirement is a **reviewed full native CLI build**, pinned
  transitive libraries, and controlled synthetic input/result tests
  before any model-backed hosted Swedish STT experiment.

Do not merge, enable or infer production readiness from this smoke test.
