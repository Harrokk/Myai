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


## Corrected, explicitly approved USB microphone capture: PASS

The user expressly approved a new and separate **one-time**
two-second USB microphone capture after correction of the
`arecord --file-type=raw` argument.

- Authorized commit: `cc25f7fec9251998b24ae61526ab48febd85d33b`
- One-time workflow: `.github/workflows/ventuno-usb-microphone-corrected-once.yml`
- Verified GitHub Actions run:
  https://github.com/Harrokk/Myai/actions/runs/38249279855
- Job ID: `114811069110`, conclusion **success**.
- **41/41 safety and mocked-audio tests passed**.
- Fresh USB ALSA metadata: capture on **card 1, device 0**
  and accessible PCM node.
- Installed `arecord --file-type=raw` command-line support confirmed.
- Exactly one real capture with `plughw:1,0`,
  16 kHz, 1 channel, S16_LE, duration 2 s, raw stream in RAM.
- Bytes received: **64,000** (32,000 16-bit samples).
- Normalized RMS: **0.023983** (~2.40% of full scale).
- Normalized peak: **0.180634** (~18.06% of full scale).
- Status: **`microphone-signal-measured`**; non-silent physical
  capture verified.
- PCM was discarded after numeric measurement, not written to
  disk, sent to a remote service, played back or transcribed.
- MyAI and GenieX remained active; production voice options stayed
  disabled; no model loaded.

**Milestone completed:** Physical USB microphone PCM capture
is working on the current VENTUNO Q hardware and ALSA mapping.

**What is not yet verified:** intelligibility or transcription of
actual user speech, VAD behavior, stable ALSA card numbering after
reboot, audible USB speaker output, acoustic echo handling,
full-duplex conversations, production voice orchestration, long-term
stability, or performance under sustained GenieX load.

The user's authorization was only for this single capture.
Do **not** rerun the capture. The next logical step is a
separately authorized, safely volume-limited physical USB speaker
test, or alternatively a no-playback metadata preflight.


## One-time user-approved USB speaker playback: ALSA success

The user gave permission to play one low-volume Swedish speaker test
using the connected USB sound card on VENTUNO Q. The dedicated
one-time workflow was triggered by the exact authorization commit
`036b85aadd80da6b6a12f9e1abc7fdcbbe91fb26` and
`github.run_attempt == 1`. It cannot repeat through an ordinary
workflow retry.

Source: `scripts/ventuno_usb_speaker_smoke.py`;
test suite: `tests/test_ventuno_usb_speaker_smoke.py`;
workflow: `.github/workflows/ventuno-usb-speaker-consent-once.yml`.

**Actual GitHub Actions run:**
https://github.com/Harrokk/Myai/actions/runs/38250308186
Job ID `114814586738`, concluded **success**.
- Exactly **28/28** targeted mock-only safety tests passed.
- USB ALSA card 1, PCM playback 0 was still accessible and `aplay`
  CLI flags were supported.
- eSpeak NG and Swedish voice data were downloaded from trusted
  distro packages and extracted only into a fresh runner temporary
  workspace; synthetic MyAI VoicePipeline-to-TTS synthesis succeeded.
- A single fixed phrase, `Hej. Jag heter My AI.`, was synthesized
  in memory, limited to at most **4% digital peak** (about -28 dBFS)
  and passed to `aplay --device=plughw:1,0 --file-type=wav`.
- WAV sample rate: **22,050 Hz**. Duration: **2.09 seconds**.
  Measured PCM digital peak after limiting: **0.039978**.
- `aplay` returned exit code 0:
  `usb-speaker-pcm-playback-completed`.
- No audio files or microphone recordings were made; no mixer
  controls written or production MyAI/GenieX voice settings changed.
  Both services remained active after cleanup of all temporary files.

**Verification boundary:** This proves the fixed Swedish test PCM
was accepted by USB playback. It does **not** prove the user could
physically hear the sound, its intelligibility or acoustic level,
full-duplex communication, microphone-to-Whisper chain, or usable
MyAI handsfree conversation. The result explicitly reports
`audible_sound_confirmed_by_person=false`.

**Next step:** Ask user if the exact one-time phrase was heard from
the USB speaker. Do not replay audio automatically without a new
request. With hearing confirmed, build a separately validated
USB input->Whisper STT->MyAI/GenieX->Swedish TTS->USB output
integration with explicit per-stage resource bounds and rollback,
without immediately enabling the production voice flags.


## User-confirmed audible USB speaker test

On 2026-10-12, immediately following successful isolated playback
run `38250308186`, the user **personally confirmed hearing**
the exact Swedish test phrase **"Hej. Jag heter My AI."**
through the connected USB speaker on VENTUNO Q.

This is direct user confirmation of **audible physical output**,
in addition to the already recorded ALSA `aplay` exit-status
success, and completes this narrow USB speaker hardware acceptance
checkpoint. The earlier test's machine-readable
`audible_sound_confirmed_by_person=false` remains historically
correct for the test *at execution time*: it could not itself
measure human hearing, and the user's subsequent confirmation
supplies that missing external evidence.

Current verified hardware:
- USB microphone capture at ALSA card 1 PCM 0
  (`plughw:1,0`): 2 s, 16 kHz mono, 64,000 bytes, non-silent
  RMS 0.023983 (run `38249279855`).
- USB speaker playback on ALSA card 1 PCM 0
  (`plughw:1,0`): fixed Swedish TTS phrase, 2.09 s WAV,
  digital peak limited to 0.039978 (run `38250308186`),
  **audibly confirmed by the user**.
- MyAI and GenieX services remained active, production voice
  flags disabled, no microphone audio persisted and no extra
  models or packages installed into production.

**Next integration milestone, not yet verified:**
a separately authorized, bounded real USB microphone utterance
→ local Swedish Whisper transcription → MyAI/GenieX response
→ temporary Swedish eSpeak synthesis → USB speaker output.
First build and unit-test the multi-stage adapter without
physical audio; preserve the existing production services and
obtain a fresh opt-in before capturing real user speech or
playing additional physical speaker audio. ALSA card indexes may
change and must be revalidated before hardware access.

This documentation change does NOT rerun physical audio or alter
the active MyAI installation.
