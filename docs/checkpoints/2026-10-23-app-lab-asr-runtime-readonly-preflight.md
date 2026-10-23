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

## Actual real-board result

**One-shot ARM64 VENTUNO run:** https://github.com/Harrokk/Myai/actions/runs/39964356804
**Frozen run HEAD:** `88cc3c86dbacf47102c6a1b99f6bb9b4025e4aea` (one-use gate).
**Conclusion:** SUCCESS.

Observed (sanitized):
- Arduino cached installed assets catalogue exists and contains `arduino:asr`.
- Exact official Whisper Small model folder exists, has a bounded, complete
  top-level directory scan with non-bookkeeping model payload; no
  `.download` incomplete-transfer marker.
- USB card 1 capture device 0 present and accessible by normal runner;
  `/dev/snd/by-id` stable reference symlink(s) exist.
- At least 10 GiB memory available at inspection.
- MyAI and GenieX production services remain active.
- `microphone_opened=false`, `asr_inference_attempted=false`,
  `docker_command_executed=false`, `services_or_config_changed=false`.

Outcome: `host-metadata-candidate-guest-npu-unverified`.
This is **not** an App Lab runtime or spoken-dialogue success. We have
not opened the microphone, run or deployed the App, or tested whether
QNN can allocate ASR alongside the active GenieX. The normal App Lab
Python container is expected to bind mount host `/dev` based on
Arduino's source, but guest enumeration has not yet been observed.

**Immediate next meaningful test:** a fresh, explicitly authorized,
operator-supervised, **one-time official ASR-only** 5s session in App
Lab. It must stop if guest USB input or model readiness fails, and
must return only safe status categories, not speech data/transcript.
No MyAI tools, second Qwen model or TTS should run in this initial
pilot. Do not auto-run that test based on this metadata result.
