# MyAI App Lab v2 – source-only first SDK PCM-capture cue, 2026-11-11

## Verified real-world state

The operator ran one explicitly authorized eight-second ASR v2 pilot on VENTUNO and reported **`empty-final-only`**. The previous explicit-ALSA run had already reached `App started` and `microphone-opened` with Razer Kraken V3 X at host ALSA card/device `1:0`. The event result proves empty final ASR text, **not** whether the user spoke inside the ASR capture window. Do not infer that Whisper Small is incompatible or that the microphone is silent.

## Official Arduino SDK source review

Reviewed `arduino/app-bricks-py` at pinned SHA `94f100ee906770e6f469f9edbc615bad895d695e`:
- `src/arduino/app_bricks/asr/local_asr.py` (`BaseASR._transcribe_stream`): before any capture, takes the session slot and calls `_create_transcription_session`, which may take >5 s while the model loads. Only after that does it launch `_transcription_session_handler` and its `_reader_thread_body`, which calls `self._source.capture()`.
- The previous message `microphone-opened` was emitted immediately after `mic.start()` and **before** the session initialization, so instructing the user to speak then was premature.
- `src/arduino/app_peripherals/microphone/base_microphone.py` exposes `capture()` returning `np.ndarray | None`; the upstream stream callback uses status transitions, but the ALSA implementation reviewed does not visibly transition from `disconnected` to `connected` at start, so relying on its `on_status_changed('streaming')` would be unproven.

## Minimal new source-only pilot

- A `FirstCaptureCueMicrophone(ALSAMicrophone)` subclass only calls `super().capture()`, checks `chunk is not None` and `chunk.size > 0`, prints one fixed `capture-started-speak-now` code and passes back the **same unmodified chunk object**.
- The old premature status becomes `microphone-opened-wait-for-capture`. This does not claim that bytes were already sent over the WebSocket.
- Fake Arduino tests prove cue after session establishment, only once for multiple captures, no cue for None/zero-byte PCM or if the ASR session creation fails, same eight-second timeout and clean mic release.
- No audio was recorded; no hardware runner, service control, TTS, GenieX/LLM, auto-deploy, or legacy voice import. The existing MyAI/GenieX services and prior archive remain unchanged.

**Physical gating:** operator must separately authorize a new recording if desired; the existing consent was consumed. If the test still produces `empty-final-only`, examine safe non-transcript metadata from ASR Brick logs around session creation and audio transmission; don't repeat sessions blindly.
