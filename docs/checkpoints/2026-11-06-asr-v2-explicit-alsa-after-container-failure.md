# VENTUNO ASR v2 startup failure and source-only microphone selection fix — 2026-11-06

## Real user-supplied observations
- New App Lab pilot crashed during Python module initialization, before `App.run`, at `AutomaticSpeechRecognition(language="sv", translate=False)` → SDK `Microphone(0)` → `_nth_plugged_microphone(0)`: `MicrophoneOpenError: No microphone found at index 0: only 0 microphone(s) plugged`.
- App Lab ASR Brick server responded to HTTP /health with 200; shutdown SIGTERM/exit0 is not proof that the model transcribed speech.
- Older App Lab ASR application **2026-11-03** used explicit `ALSAMicrophone("plughw:1,0")`; microphone opened, first PCM chunk observed and level categorized present, but ASR returned `no-final-text`.
- VENTUNO host read-only preflight on 2026-11-06 showed one USB capture device and both `myai-geniex` and `myai-ventuno` active; did **not** expose current card/device index and did not verify capture in the App Lab container.
- Whisper Small (quantized) availability was operator-reported via UI. No actual ASR accuracy result yet.

## New v2 patch (source-only)
- Replace default `AutomaticSpeechRecognition(language="sv")` with official SDK-provided, explicitly selected `ALSAMicrophone(device="plughw:1,0",shared=False,auto_reconnect=False)` passed as `mic=mic`. This bypasses automatic ordinal selection `Microphone(0)`; it does **not** bypass SDK ALSA device validation and may still fail if App Lab cannot see it.
- Manage caller-owned `mic.start()/stop()` once per separately authorized session; `asr.cancel()` and mic stop both in cleanup even on failure. One finite 8s Swedish sentence stream, no fallback to other devices or repeated captures.
- Categorize mic start, ASR errors and mic release failures without logging private words. Source-only synthetic fake SDK tests cover ownership/order, one capture, malformed final, exception boundaries, cancellation and cleanup.
- Retain all old code, Git history and production config unchanged; no service control, physical test, model installation or TTS.
- Future physical prerequisite: read-only check that current USB ALSA card is still **1,0**, and separate user approval for one new recording. If multiple mic routes, abort and identify exact stable card rather than guessing.

Vendor source reviewed: `arduino/app-bricks-py` at commit `94f100ee906770e6f469f9edbc615bad895d695e`, particularly `src/arduino/app_bricks/asr/local_asr.py` for source ownership and `src/arduino/app_peripherals/microphone/alsa_microphone.py` for explicit ALSA refs.
