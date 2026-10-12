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
