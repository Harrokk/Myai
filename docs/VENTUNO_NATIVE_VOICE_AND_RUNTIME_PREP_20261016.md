# VENTUNO Q native voice + runtime preflight, 2026-10-16

**Scope:** DRAFT PR #247 stacked above #242. Everything below is limited to disposable working directories or unit tests. No microphone, playback stream, real STT weights, GenieX service request, NPU, privileged package management, or production MyAI deployment occurred.

## Phase 1: pinned and compatible ARM64 Python

A source-code compatibility issue was found: the former 28-wheel lock selected `av-19.0.1` even though our checked-in Faster-Whisper 1.2.1 staging path expects PyAV 18.x. `requirements-voice.txt` now explicitly constrains `av>=17,<19`; both locked files select the **hosted-resolved exact binary PyAV 18.1.0 ARM64 artifact and SHA-256**. All 28 wheels are pinned to exact versions/hashes, selected on hosted Linux and installed **only** in a new temporary Python 3.12 ARM64 virtual environment on the VENTUNO Actions runner. The installation succeeded under RAM/disk bounds and a wall-clock deadline. This is not a production installation.

The first unmodified native package import on the VENTUNO saw 6 of 7 direct modules importable; `sounddevice` returned a sanitized `OSError` because its system-level PortAudio runtime was not discoverable. Measured peak RSS of this import process was **58.2 MiB**, which is only library import memory, **not** Whisper model memory.

The existing, reviewed `scripts/ventuno_portaudio_temp_stage.py` then fetched official distro **libportaudio2** and **libjack-jackd2-0** packages without elevated privileges, extracted them **only** to the disposable staging directory, and performed a `sounddevice` import with a child-local temporary library resolver. This was **successful**:
`sounddevice-imports-with-temporary-portaudio`. No ALSA stream was opened; the general board production installation remains unchanged.

**Limits:** Although all seven imports are now individually proven when PortAudio/JACK are supplied in staging, this does **not** prove the production system can find PortAudio, that real microphone I/O works, or that Faster-Whisper can load/cache a model and decode on this board.

## Phase 2: synthetic Swedish reply

The existing `ventuno_tts_temp_stage.py` fetched allowlisted official eSpeak NG distro packages to a separate temporary directory without global installation, and rendered **one fixed Swedish phrase** to an in-memory WAV. It verified the actual `VoicePipeline` assistant-to-TTS bridge with a synthetic STT transcript and dummy LLM; results:

- `isolated-swedish-tts-signal-verified`
- `myai_voice_pipeline_synthetic_bridge_verified=true`
- `swedish_pcm_synthesis_verified=true`
- WAV: **22050 Hz**, approximately **2.09 s**, non-silent (RMS fraction **0.089433**)
- `microphone_used=false`, `audio_written_to_disk=false`, `physical_playback_verified=false`

This proves synthetic STT input -> fake assistant -> real MyAI VoicePipeline -> genuine offline eSpeak WAV output, **not** real STT model inference, production pyttsx3 engine operation or audible speaker output.

## Phase 3: loaded configuration + startup failure recovery

In `core/runtime_service.py`, startup previously set `running=True` before the initial heartbeat write, with no cleanup on heartbeat failure; a partially started runtime could remain running. The new fail-closed fix calls `stop(emit_heartbeat=False)` to stop started components if initial heartbeat writing throws, then re-raises the original failure. New synthetic tests verify active component stop, false running status and one heartbeat attempt, and that the isolated voice profile writes only a scoped heartbeat without creating SQLite.

**Limit:** The installed live service is **not** running this DRAFT code. Actual in-memory configuration attestation, production service outage recovery and externally verifiable rollback cannot be claimed until an explicit, separately approved deployment.

## Phase 4: Actions and authorization

Four historical main-only workflows remain replaced by inert, disabled placeholders in the DRAFT integration candidate; no main/default branch write was performed. The new temporary native-import workflow has a hard exact-SHA checkout, ARM64/user identity, minimum available RAM/disk, isolated parent/venv path, no privileged installers, bounded subprocesses and mandatory cleanup. All physical audio, NPU and live service workflows require independent authorization.

## Phase 5: release decision

**DRAFT ONLY.** Before selecting a deployable image or scheduling full physical voice/HTP testing, require: final full project ARM64 CI for this exact HEAD, operator-reviewed release diff, separate staged installer and rollback, verification of active in-memory settings, native PortAudio/eSpeak availability in the *chosen* runtime without modifying services unexpectedly, and explicit physical consent.

**NPU operator profiling remains NO-GO** until HTP/QAIRT driver/model compatibility, exclusive maintenance and independent physical recovery are verified. No stage of this work is a license to start it automatically.

### CI evidence

- Hosted pinned PyAV 18 wheel resolution: `https://github.com/Harrokk/Myai/actions/runs/38926317046` (success)
- Real disposable ARM64 hashed-wheel install/import, temporary PortAudio and in-memory Swedish TTS: `https://github.com/Harrokk/Myai/actions/runs/38927510336` (success)
- Exact branch final full suite is mandatory after all code/document changes; quote only its verified final SHA/run, not an older run.
