# VENTUNO first-party App Lab ASR startup preflight, source-only

Date: 2026-10-23. Builds on approved installation DRAFT PR #367.

The official model installer completed on the real board via
`arduino-app-cli model install whisper-small-quantized`, verified by
the same official CLI listing status `installed` (run 39956949300).
Both MyAI and GenieX remained active.

Actual first-party runtime sources reviewed:
- `arduino/arduino-app-cli/internal/orchestrator/compose_template.go`:
  main App Lab Python service mounts host `/dev` to `/dev`, adds
  `audio`, `fastrpc`, `render` groups and ALSA/HTP cgroup rules.
- `arduino/app-bricks-py/src/arduino/app_peripherals/microphone/alsa_microphone.py`:
  an explicit `plughw:1,0` is first resolved to a stable
  `plughw:CARD=<card-name>,DEV=0` reference **only if the SDK sees that
  capture PCM**. It is *not* blindly opened by ALSA on any card.
  The conversion is not evidence of App Lab guest enumeration.
- `arduino/app-bricks-py/src/arduino/app_bricks/asr/local_asr.py`:
  caller-owned microphone must be explicitly started/stopped by
  the pilot and is not owned by the ASR Brick; pilot in PR #363
  already corrected this and tested it.
- App Lab ASR can warm the model on the NPU before user_loop.
  The model's installed state **does not** certify runtime
  inference or concurrent GenieX QNN context allocation.

This PR executes one **strictly read-only** board metadata check:
- correct USB ALSA capture pair 1:0 and current-user capture node
- `/dev/snd/by-id` presence and available sound-card metadata;
- actual official Whisper model's default folder and non-bookkeeping
  top-level content, no raw model files or speech opened/read
- cached Arduino installed assets catalogue for ASR, at most 16
  release entries scanned, no full listing/CLI process
- active MyAI/GenieX services and a coarse memory band.

These checks are a **host-only candidate**. There is no
mic/audio open, App Lab container startup, ASR model load, Docker
run/exec/inspect, network listener, download, or production writes.
Even perfect metadata does **not prove** App Lab's actual guest mic
permissions, model startup, NPU coexistence, Swedish recognition,
or TTS. Only a newly approved physical one-shot pilot can test those.

Next action after reviewing status: propose **one supervised**
5-second official ASR-only voice test with mic device
`plughw:1,0` and model `whisper-small-quantized`; no model
downloads or LLM calls, logs limited to sanitized categories.
Do not launch this without fresh explicit microphone consent.
Keep all PRs DRAFT pending physical evidence.
