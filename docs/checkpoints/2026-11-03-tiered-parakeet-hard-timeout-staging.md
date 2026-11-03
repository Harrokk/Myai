# MyAI STT hard deadline staging – 2026-11-03

**Status: GitHub-only DRAFT, off by default. Never install or enable on VENTUNO
without new operator consent and full security review.**

Base: DRAFT PR #376 `dev/voice-tiered-provenance-guard-20261103`,
commit `7dfc1c97951f027ec244968aa1619cb54b917844`.
Branch: `dev/voice-tiered-parakeet-isolation-20261103`.

## Changes

1. `core/voice_stt_bounded_io.py` and `core/voice_stt_process.py`:
   optional nonblocking cancellation events for the existing bounded,
   full-duplex isolated STT pipes. Check the stop signal during blocked
   pipe reads/writes and child-exit wait, and kill/reap the entire owned
   process group before returning. Original FasterWhisper call sites
   without a cancellation event keep existing behavior.
2. `core/voice_parakeet_isolated.py`: strictly opt-in, pinned Parakeet
   one-shot CPU adapter. Requires **explicit trusted offline preflight**
   (a known four-file SHA256 manifest), then fast model-metadata checks
   per request. It refuses concurrent calls, unprepared weights,
   oversized/non-PCM audio and reuse of a canceled session.
3. `core/voice_parakeet_worker.py`: checked-in, fixed `python -I`
   child. Revalidates strict argv schema and full SHA256 weight hashes
   **inside the subprocess deadline** before CPU model inference.
   Child only can receive optional RLIMIT_CPU/RLIMIT_AS. Bounded PCM is
   in memory, and output is only sanitized, schema-checked STT JSON.
   The `language=sv` reply denotes the *configured expected input*,
   not Parakeet's independently measured language.
4. `core/voice_session.py`: a future explicit tiered voice session
   can send Stop to one-shot isolated STT and refuse unsafe cleanup/
   restart, without affecting the default disabled tiered flow or
   the existing FasterWhisper and persistent worker behavior.
5. Tests for stop before process creation, cancellation during blocking
   IPC and post-EOF child wait, resource configuration, expired or
   tampered preflight, process concurrency/Stop, fixed worker entrypoint
   with a fake native recognizer, private error redaction and session
   cleanup. All fixture audio and model files are synthetic.

## Deliberate exclusions

- No physical microphone, speaker, GenieX invocation, real model weights,
  package installation, model download or Ventuno/self-hosted workflow.
- No factory/VoiceSession wiring that would actually instantiate the new
  isolated Parakeet provider. `risk_tiered_verification_enabled` stays
  `false` and `config_validation` still **rejects enabling it**.
- No real Canary, Whisper, NPU or three-independent-model concurrency.
- Critical voice commands remain blocked regardless of STT consensus.

## Risks still to resolve

- **Memory:** RLIMIT_AS is virtual address space, not physical RSS.
  Per-model RAM/CPU/temperature and cumulative GenieX headroom require
  controlled measurements. Linux cgroups are stronger isolation than
  rlimits and process groups if an untrusted descendant escapes its group.
- **Latency:** one-shot native model startup and SHA256 verification occur
  per speech segment in the child; the hard deadline bounds them but does
  not make them fast. Separate trusted preflight takes place before voice
  start, not during the synchronous audio question. Evaluate persistent
  bounded workers only after robust process cleanup, same-request nonce,
  and memory handoff review.
- **Security:** provider receives expected (not detected) language;
  independent model and speaker authentication are separate. Trusted
  manifest values must be reviewed out-of-band and the model tree
  protected against same-user mutation.
- **Hardware readiness:** exact ARM64 binary dependencies and quality of
  real Swedish transcriptions on VENTUNO are not established.
- **Release:** hosted test green is necessary but NOT sufficient.
  Independent security review, observed hard-timeout/resident-memory
  profiling and explicit operator approval are required before deployment.

This branch is staged above DRAFT PR #376, not a production merge request.
