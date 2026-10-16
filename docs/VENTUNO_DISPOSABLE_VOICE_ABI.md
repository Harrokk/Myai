# MyAI – disposable VENTUNO ARM64 voice test and physical gate (2026-10-16)

**Branch/PR:** DRAFT #243, stacked on #242. All tests use exact-SHA disposable checkouts. **No changes to main, systemd, installed MyAI venv, default configuration or NPU**.

## What was actually run

- All **28 SHA-256-pinned CPython 3.12 ARM64 voice wheels** were resolved, checked and *actually installed* into a newly created, private VENTUNO runner-temp venv. `pip check` passed. The venv and wheel downloads were deleted at the end, whether successful or failed.
- `numpy`, `av`, `ctranslate2`, `webrtcvad`, `faster_whisper`, `pyttsx3` and `onnxruntime` all imported successfully as individual limited-time child processes. This is a **native import test**, not voice/LLM model inference, TTS playback or sound-card access.
- `sounddevice` failed import with a **native shared-library loader error**. An independent read-only check reported **PortAudio not resolvable**, **ALSA resolvable** and **eSpeak-NG resolvable** on the board. This is an actual **NO-GO for the normal SoundDeviceMicrophone path**, not evidence that Whisper or CTranslate2 failed.
- A source-only checker additionally reads the distro's `apt-cache policy libportaudio2` candidate as a sanitized boolean. It does **not** install packages, modify APT indices or open a library. Whether a distro candidate is available must be established by the next actual board run.
- A complete **synthetic PCM → STT → assistant → fake TTS → VoiceSession-style Stop** regression runs on hosted Linux, with error/Stop denial tests. *No speech was captured, synthesized or played.*
- Real `MyAICore` SQLite was initialized under a disposable trial root; production-like sentinel SQLite data in a separate path remained byte-for-byte unchanged. Runtime path checks reject symlink ancestors and path traversal. This tests confinement under controlled roots, **not** a production failure injection or power-cut restoration.

## Important limits

1. Missing system PortAudio is a real blocker. Do not silently install OS libraries or launch a physical mic test. A separately approved, compatible distro package/staging procedure is needed; test library loading and routing afterwards.
2. Native `faster_whisper` import does not prove a real Whisper Tiny model can be loaded under actual memory and thermal budgets. No model weights downloaded.
3. Crash/power-cut may still strand NamedTemporaryFile WAV bytes; the normal exception-path WAV cleanup is tested, but unexpected SIGKILL/host power loss is not a validated privacy guarantee. Runtime rollback, service recovery, detached native child containment and out-of-band recovery remain separate required gates.
4. Existing runtime heartbeat source can report **future** effective loaded settings, but this PR did not deploy it, restart MyAI or attest settings held by an already-running process.
5. The four main-only workflows remain quarantined in the integration DRAFT. Final release approval still needs policy/permission and version/rollback checks on the selected final SHA. No merge to main.
6. All native imports use **private temporary installation** and NO model, mic, speaker, TTS engine, LLM or NPU execution. `pip check` verifies Python dependency metadata; it does not independently certify distro native ABI beyond the observed import successes.

## Next safe order

First establish the signed OS PortAudio package candidate in read-only metadata and prepare a reviewed, operator-approved way to provide the native `libportaudio.so.2` ABI without unplanned system mutations. Re-run disposable imports. Then complete synthetic process crash-/SQLite recovery tests and freeze the release candidate, while all physical audio and NPU tests remain separately consented and NO-GO.
