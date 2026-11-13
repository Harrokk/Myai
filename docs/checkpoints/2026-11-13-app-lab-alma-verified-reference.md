# 2026-11-13 — User-verified VENTUNO App Lab Alma reference and staged private text handoff

Status: DRAFT / source-only, not deployed. No code in production MyAI, GenieX or the working App Lab applications has been changed. Prior one-use permission for the separate microphone pilot is consumed.

## Verified by operator (not reproduced by CI)

The operator reports that a locally imported, modified Arduino App Lab application now supports successful spoken Swedish input without a wake word, local Qwen response generation, and comfortable Swedish spoken output using Piper's Alma voice on their VENTUNO Q.

Original project: https://github.com/mcmchris/keyword-asr-local-llm-kokoro-tts/tree/v1.0.3
Original App Lab ASR pattern: AutomaticSpeechRecognition(mic_asr), no explicit language override, transcribe_stream(duration=7) with partial-text fallback. The operator's derivative removed keyword detection and replaced Kokoro with Piper Alma.

The actual working ZIP and model weights were not supplied to GitHub. Exact ZIP hash, dependency versions, source parity and reproducibility are not independently verified. The source-only v1.0.3 reference is not proof that App Lab's ASR and MyAI's native FasterWhisperSTT are identical. The earlier forced-sv WAV failure root cause is still unproven.

## Already implemented in MyAI

- modules/voice/piper_alma_provider.py and core/voice_factory.py contain an opt-in local Alma provider, subject to explicit local model path and audio output device.
- config/profiles/ventuno_q.json already selects GenieX/Qwen but voice.enabled and tts_enabled remain false.
- core/assistant.py handles MyAI memory, tool planning, voice safety and execution reporting; no second assistant brain is added here.

## New source-only adapter

core/app_lab_voice_handoff.py supplies AppLabFinalTextHandoff, default disabled. It receives only one private final text after the caller states that an operator-authorized session is active and the ASR resource was released. It does not import Arduino, open a mic/speaker, expose a network port, load a model or initialize MyAI. A callable Stop probe is required and rechecked after the core response. Duplicate dispatch attempts on the same instance are rejected. Inputs are bounded; errors do not echo source transcripts.

It invokes the pre-existing MyAICore.respond_voice interface with a verifier that never approves effectful tool plans. Existing allowlisted-read-only policy still applies. It returns an answer only in the trusted caller's memory and preserves blocked/review-required states; this commit performs no playback.

The session_active and asr_released flags are cooperative contracts only, NOT authentication or proof of audio closure. This code cannot be connected to the separate App Lab container without additional review of authenticated local IPC, data isolation, audio ownership, Stop semantics, feedback/echo and concurrency.

MyAICore itself can write memory and audit/health records according to its configured policy when enabled. That must be explicitly reviewed for the actual deployment. No source change or production configuration enables the adapter here.

## Test gates and release policy

- 19 isolated/mock-only tests cover defaults, one-shot behavior, concurrent delivery, cancellation, private error messages, nonapproval of effectful plans and blocked/review-required statuses.
- Full hosted ARM64 source CI still required on exact PR head.
- No GitHub Actions workflow touches the board; no microphone permission is inherited.
- Working App Lab Alma app, production MyAI, GenieX, original apps and default branch are untouched.
- An independently reviewed authenticated IPC bridge and a separate user-approved cutover are needed before the adapter can be used live.
