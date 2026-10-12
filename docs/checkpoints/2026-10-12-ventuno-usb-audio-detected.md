# VENTUNO Q USB microphone + speaker – hardware discovery (2026-10-12)

## Verified on actual hardware

The user connected a USB microphone and speaker to Arduino VENTUNO Q.
The **read-only** hardware inventory on the VENTUNO Q self-hosted
GitHub runner completed successfully:

- Workflow: `.github/workflows/ventuno-usb-audio-readonly.yml`
- GitHub Actions run: https://github.com/Harrokk/Myai/actions/runs/38247956223
- Diagnostic script: `scripts/ventuno_usb_audio_inventory.py`
- Regression suite: **9 passed**.
- USB ALSA card index: **1** (index may change after unplug/reboot).
- Capture PCM: **card 1, device 0** – potential `plughw:1,0`.
- Playback PCM: **card 1, device 0**.
- Both associated /dev/snd PCM character devices existed and were
  readable and writable by the runner.
- MyAI and GenieX production services remained active.
- **No microphone audio recorded, no speaker playback started, no mixer
  settings written, no changes to active profile, no model installed.**

## Conclusions and boundary

This proves Linux ALSA enumerates **one USB sound card with both capture
and playback PCM interfaces** and exposes corresponding device nodes
to the runner. It does **not** prove that the attached microphone
actually captures sound, that the playback hardware outputs audible
sound, or that an ALSA PCM stream can be opened in the desired format.

Before enabling MyAI voice:

1. Get **new explicit authorization** for a one-time, two-second,
   in-memory microphone signal-level diagnostic on the discovered USB
   capture pair; no waveform or transcript retained or sent.
2. The current `scripts/ventuno_microphone_smoke.py` deliberately
   restricts explicit devices to the **old internal**
   `plughw:0,1`. Do not reuse or bypass this gate. Update and test
   its USB target allowlist/dynamic discovery with fresh safety tests
   before any new authorized hardware capture.
3. Verify USB ALSA card index again just before opening a stream,
   since the index can change. Prefer a stable ALSA device selector
   when validated (not an assumed permanent numeric card index).
4. Independently test the actual speaker with consent, controlled
   volume, fixed short synthesized sound and rollback.
5. Only after both endpoints are proven, configure a reversible
   voice pipeline, without automatically enabling production flags.

All current voice production settings remain disabled. The earlier
on-board `hw:0,1` ALSA `alsa-capture-nonzero` issue does not
automatically apply to this newly enumerated USB device.


## One-time consented physical USB microphone attempt

On explicit user approval, we created the single-purpose workflow
`.github/workflows/ventuno-usb-microphone-consent-once.yml` with a
one-time exact commit-message gate and `github.run_attempt == 1`.

- Authorized commit: `3abdf734b5f34dfd2df98f8ca72d0613b8ad4342`.
- Actual VENTUNO job:
  https://github.com/Harrokk/Myai/actions/runs/38248566824
- **41 targeted automated tests passed.**
- The VENTUNO USB card and accessible capture PCM remained **1:0**;
  the active production voice flags remained disabled.
- The `arecord` subprocess was **invoked once**, but exited nonzero
  before a complete 64,000-byte PCM capture could be validated.
  Reported status: `alsa-capture-nonzero`, error category:
  `unclassified`.
- Both MyAI and GenieX services stayed active. No audio data was
  retained, transmitted, displayed, or transcribed.

**Root-cause candidate identified immediately afterwards:** both old
internal and new USB microphone scripts called `arecord` with
`--type=raw` (unsupported option name); ALSA's documented flag is
`--file-type=raw`. This explains why both calls may have returned
nonzero extremely quickly; do not assume either microphone hardware
is defective solely from those failed attempts.

Source files and tests have been corrected to enforce
`--file-type=raw`:
- `scripts/ventuno_microphone_smoke.py`
- `scripts/ventuno_usb_microphone_smoke.py`
- both corresponding regression test modules.

A separate **no-recording** workflow,
`.github/workflows/ventuno-arecord-options-readonly.yml`, was
introduced to verify the installed `arecord --help` output contains
the supported flags and run mock-only tests. Its result must be
checked before any future physical recording.

**Consent boundary:** The user approved this *one* two-second
physical attempt. The workflow ran, the result was inconclusive,
and **no second physical recording is authorized** by this
checkpoint. Do not rerun the one-time workflow or create another
capture job without a new explicit user approval. The corrected
source files do not change active production voice settings.


## Corrected arecord CLI option verified on VENTUNO

Read-only GitHub Actions run:
https://github.com/Harrokk/Myai/actions/runs/38248872064

- Workflow conclusion: **success**, checked from GitHub jobs/logs.
- Installed `arecord --help` confirms these six flags:
  `--file-type`, `--format`, `--rate`, `--channels`,
  `--duration` and `--device`.
- **41 tests passed** using only generated/mocked audio bytes;
  no physical capture or playback occurred.
- Services stayed active; changes remain on development branch only.

The documented `--file-type=raw` correction has therefore passed
hardware-local command-line preflight, but **actual USB microphone
signal quality after this correction has not yet been tested**.
A fresh, explicit user approval is required for another real
two-second recording.
