# Final USB audio sysfs read-only diagnostic — 2026-11-04

Stacked on PR #395 (SHA c4b694f0e4df427278223d0186dfd63346b7e3e8). This diagnostic is a **single, branch-scoped, read-only physical metadata check** under the existing operator authorization to continue evaluating VENTUNO. It cannot trigger audio, model, driver or service execution.

Verified previous source and board evidence:
- PR #394 physical metadata run #41809221114: GitHub self-hosted runner `ventuno-q` really reached. MyAI active, GenieX active, RAM available 13.47 GiB, disk available 26.93 GiB, max temperature 38.0 C. USB audio metadata NO-GO. No mic/audio or production changes.
- PR #395 USB/ALSA numeric inventory run #41809577583: hosted safety and board metadata jobs SUCCESS. `usb_audio_card_indexes=[]`, `usb_capture_pairs=[]`, `usb_playback_pairs=[]`, `read_write_accessible_capture_pairs=[]`, `read_write_accessible_playback_pairs=[]`. `arecord -l` reported non-USB capture pair `[0,1]`. The configured expected USB duplex pair `[1,0]` was unavailable. `production_voice_disabled=true`, no audio was opened.

This last read-only workflow samples only USB kernel **numeric bInterfaceClass** values, whether interfaces of class `01` (USB Audio) are bound to `snd-usb-audio`, presence of the `snd_usb_audio` module and aggregate ALSA USB-card count. No vendor/product IDs, serial numbers, device paths, driver names of unrelated devices, secrets, filenames, raw exceptions or USB labels are logged.

Interpretation:
- Audio class interface count = 0: no USB Audio Class interface is enumerated. Operator should physically inspect and reconnect the headset/microphone, port, power and cable.
- Audio class interfaces > 0 but bound count = 0: USB device is visible but audio driver is not bound; **no automatic module load** is authorized.
- Bound audio interfaces > 0 but no ALSA USB cards: driver/ALSA routing problem; stop without permissions or service changes.
- Interfaces and ALSA card present: repeat a separately authorized metadata-only USB ALSA readiness check before requesting fresh audio consent.

Even a green workflow or enumerated USB class is **NOT** permission to capture audio, enable voice, install packages, change group memberships, restart GenieX or perform NPU inference. No automatic retries, no production merge. Risk-tiered voice remains OFF and critical actions remain denied.

Record the exact SHA and run evidence once concluded. If absent USB class, the remaining blocker is physical and cannot be safely resolved by unattended remote software commands.
