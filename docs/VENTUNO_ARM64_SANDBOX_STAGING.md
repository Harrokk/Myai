# VENTUNO ARM64 voice dependency and synthetic-stage verification

## Strict isolation and scope

This DRAFT does **not** install any voice package in the physical VENTUNO's
`/home/arduino/MyAI/.venv`, run models, open ALSA/PortAudio, drive the NPU,
restart a service, merge into main or authorize any user audio.

The workflow `.github/workflows/ventuno-arm64-voice-sandbox.yml` has two
independent jobs:

1. **GitHub-hosted ARM64 machine**, Python 3.12 and temporary private venv.
   Download the exact 28 SHA-256-pinned voice wheels with source distribution
   disabled and dependency resolver disabled, compare all 28 filenames and
   file hashes, install **only** from the verified local wheel directory into
   the disposable venv, run `pip check`, and import (but **not initialize
   or run**) Whisper, sounddevice, WebRTC-VAD, pyttsx3, CTranslate2, PyAV
   and NumPy. No sound device is opened. The temporary venv is discarded.

2. **GitHub-hosted x86 Linux machine**, isolated temporary pytest venv.
   Inject fake mic, VAD, STT, assistant and TTS components into the real
   `VoiceSession` and `VoicePipeline`, then test short synthetic PCM,
   transcript, voice response, non-hardware TTS, Stop and a faulted STT.
   Also run existing session, pipeline and remote-stage tests.

**Important:** GitHub-hosted ARM64 is not the Qualcomm VENTUNO board. Its
`glibc`, PortAudio/eSpeak and DSP drivers may differ; native imports on a
hosted ARM64 machine are an ABI *screen*, not proof of the board's runtime
or of a usable microphone device. No actual CTranslate2 model is loaded.
`sounddevice` is imported only; no streams/devices are enumerated or
opened. `pyttsx3.init()` is never called.

## Completion criteria still not met by these jobs

- Native ABI in a disposable VENTUNO-local venv needs explicit isolation,
  memory/runner lifecycle and cleanup controls, followed by read-only proof
  that installed production services/configuration remain unchanged.
- Crash interruption during native STT is a distinct hazard. A synthetic
  `Stop` path does not establish detached subprocess/process-tree cleanup.
- A safe future in-process heartbeat is not proof of current, pre-upgrade
  MyAI settings. Actual runtime is unchanged.
- The four main-only historic GitHub jobs are inert in the integration
  candidate, but a final allowlist of all legacy hardware workflows and
  protected rollout policy is required before a production merge.
- NPU/HTP profiling and real microphone/speaker STT→LLM→TTS require their
  own new operator consent and verified recovery.

**Result labels:** never interpret a green synthetic or hosted ARM64 CI
as authorization to deploy, to start a microphone or to profile an NPU.
