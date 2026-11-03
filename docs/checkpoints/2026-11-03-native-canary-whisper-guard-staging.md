# MyAI native Canary/Whisper candidate hardening checkpoint – 2026-11-03

**Status: source-only, DRAFT, DEFAULT OFF, explicit enablement denied.**
Base: DRAFT PR #379, commit `ee9003fb99dba69eb69323c00f68608858d2c875`.
Branch: `dev/voice-candidate-native-guard-20261103`.

No VENTUNO commands or self-hosted workflows, no installations, no model
downloads, no live microphone, no real Canary/Whisper inference, no GPIO
activity, no changes to running GenieX services.

## Source-verified CLI contracts

- Canary 1B v2 uses transcribe.cpp `transcribe-cli` with a Swedish source
  hint `-l sv`, `--task transcribe`, CPU backend, fixed threads, and a
  single 16 kHz mono WAV input. The single-file upstream driver emits
  `run: ok` and one `text:` result, not a guaranteed JSON object.
  Source inspected: `examples/cli/main.cpp`, `asr.cpp`, `src/transcribe.cpp`
  at upstream main on 2026-11-03; pin exact upstream Git revision before
  production release and confirm the CLI output against the built binary.
- Whisper large-v3 Turbo uses whisper.cpp `whisper-cli` with fixed CPU
  arguments, Swedish source `-l sv`, `-oj -of -` for JSON emitted to stdout
  and no text-result file, `-np -nt`. Its JSON includes params,
  result.language, and transcription segments. Source inspected:
  `examples/cli/cli.cpp` at upstream master on 2026-11-03.
- Current profiles remain the exact model/ELF files pinned by PR #378.
  Dynamic-library closure and binary build provenance are NOT yet verified.

## Staged modules

1. `core/voice_candidate_cli_contract.py` constructs only exact known
   Canary/Whisper command arguments. No shell, custom model/plugin/runtime
   option, translation, GPU, audio paths except `/proc/self/fd/N`.
   Parsing is **fail closed**: unknown or duplicate status/text lines,
   Canary incomplete/truncated output, illegal controls, changed language,
   duplicated/malformed Whisper JSON, invalid transcription fields and
   oversized output yield no vote.
2. `core/voice_candidate_worker.py` is a fixed Python `-I` child. It
   validates the private inherited sealed WAV descriptor and 44-byte PCM16
   format, applies child RLIMIT settings, checks actual model + native ELF
   hashes against independently pinned manifests, then execve's the
   fixed verified native executable. Errors produce only a generic exit
   code; no private audio/path/output details printed.
3. `core/voice_candidate_native.py` provides an isolated opt-in STT class.
   The parent creates WAV in a sealed Linux memfd from PR #379, explicitly
   hands only that fd to the child, launches a new owned process group,
   captures bounded (32 KiB) stdout, enforces a single hard monotonic
   deadline, checks Stop at short intervals, requires child exit=0 and
   complete group cleanup, rechecks model identity, then parses only the
   expected output shape. No worker persists between utterances.
4. Tests use tiny synthetic model files and fake ARM64 ELF headers and
   disposable shell-free Python child processes to exercise IPC,
   cancellation, hard timeouts, malicious output, child exit failures,
   invalid model digests, late revocation and the child argv contract.
   **No real candidate binary is executed by tests.**

## Important remaining release blockers

- Canary and Whisper native input support for Linux memfd paths
  `/proc/self/fd/N` has NOT been exercised with the actual C++ CLIs.
  Their actual console outputs and exit codes must be validated on a
  pinned reproducible build before they can become trusted STT voters.
- The dynamic library dependency graph/loader, native ELF build provenance,
  cgroups (including any descendants escaping the process group),
  memfd swap behavior, memory pressure and operating permissions must be
  independently reviewed; model and executable SHA-256 alone are
  insufficient to prove that arbitrary dependencies are trusted.
- Actual Swedish quality (WER, negation, numbers, filenames and speaker
  variability), response latency, RSS, NPU/CPU contention and GenieX
  handoff have not been measured on VENTUNO. Simulation is not hardware
  verification.
- `voice_factory.py`, VENTUNO configuration, user-facing voice services
  and production authorization remain untouched. Tiered verification
  cannot be enabled by config validation, and critical voice-controlled
  actions stay blocked awaiting separate identity/approval.
- Two independent audit passes and exact-HEAD hosted ARM64 CI must succeed
  before further promotion. A hardware pilot requires explicit operator
  authorization. DRAFT PR must not be merged or deployed automatically.
