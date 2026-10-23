# VENTUNO App Lab host-readiness metadata pass (2026-10-23)

**DRAFT / source-only except one read-only host metadata job.**
This checklist is a prerequisite for the official Arduino App Lab ASR pilot in PR #363.

## Corrected official SDK ownership contract

Source: https://github.com/arduino/app-bricks-py/blob/main/src/arduino/app_bricks/asr/local_asr.py

- `App.run()` starts registered ASR Brick and its NPU model warmup before invoking the application's user loop.
- If `AutomaticSpeechRecognition(mic=...)` receives a caller-provided microphone, `_owns_source=False`. **ASR does NOT call `mic.start()` or `mic.stop()`**. The pilot now explicitly starts and stops it inside the one-shot user loop, and its mocks verify release after both successful and failed transcription.
- That correction supersedes the previously exported ZIP for PR #363, which did **not** correctly start an injected microphone. Do not run the older ZIP.

## Read-only host preflight

Workflow `.github/workflows/ventuno-app-lab-host-metadata-20261023.yml` will run once on the existing VENTUNO Actions runner after this checkpoint is committed; it is NOT a voice test. It only reads `/proc/asound/pcm`, `/proc/asound/card1/usbid`, `/dev/snd/pcmC1D0c` device attributes, `/proc/meminfo`, and sanitized `systemctl is-active` for existing services. No model import, no microphone open, no `arecord`, no `docker`, no ALSA playback, no audio or user transcript, no listening socket, no login/session data, no Git checkout or production changes. Script exits after a bounded single pass. Outputs booleans and coarse free-memory band only, never hardware IDs or user paths. One-shot push gating must protect against replay and later commits.

Even if host ALSA 1:0 exists, it **does not verify** App Lab container ALSA namespace or device mapping. Even if 10 GiB or more memory is available, it **does not prove** concurrent ASR QNN model and GenieX NPU session load works. App Lab installed image/model state remains unknown without a separately approved read-only container inspection.

## Decisions

1. Keep production `myai-geniex.service` and `myai-ventuno.service` unchanged.
2. Never bind GenieX to `0.0.0.0` to bypass App Lab network namespace restrictions.
3. Never run the new App Lab microphone, download model, start another LLM or TTS based on this host-only pass.
4. Confirm App Lab container microphone identity and model installation before any **separately authorized** supervised single-use ASR test.
5. Keep PR stack DRAFT and NO-GO for main merge/production rollout.

## Actual read-only VENTUNO result

**One-time run:** https://github.com/Harrokk/Myai/actions/runs/39952787653
**Workflow source at run:** `358f4a1f3c786b8d5898c195d751a2d508609a06`
**Result:** SUCCESS.

Sanitized observed results:
- Expected host ALSA capture **card 1, device 0 present**; card 1 classified as USB.
- `/dev/snd/pcmC1D0c` is a character device accessible read/write by existing runner user.
- Both `myai-geniex.service` and `myai-ventuno.service` remained active.
- `MemAvailable` fell in coarse band **at least 10240 MiB**.
- Explicit flags `microphone_stream_opened=false`, `speaker_stream_opened=false`,
  `npu_model_loaded=false`, `production_modified=false`.

The result is **`host-metadata-candidate-container-unverified`**, NOT
`ASR-ready`. Cannot establish which audio card exists inside the
Arduino App Lab container; the runner is in a different environment.
Likewise the installed Whisper model and actual GenieX/ASR NPU
coexistence remain unverified. No physical audio pilot may start on
these readings alone.

## Pure source regression

The separate hosted ARM64 CI for the corrected PR #363 HEAD
`a919d82dd4f0a35e223c600712918aa282591ca6` at
https://github.com/Harrokk/Myai/actions/runs/39952442291 completed
**4376 passed, 7 skipped, 0 failed**. This is an injected mock SDK,
not a verification of the installed board's actual Arduino App Lab
package version or microphone performance.
