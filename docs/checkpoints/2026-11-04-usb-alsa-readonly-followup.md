# Follow-up on-device USB / ALSA inventory — 2026-11-04

The first operator-authorized VENTUNO read-only preflight on PR #394 at SHA eff996bfa52374e19d3ce14494afcc6e8dc56538 **reached the real runner** and the hosted safety stage passed. The board deliberately returned **NO-GO**: USB audio absent in the fixed-route assessment. Sanitized observations: MyAI service active, GenieX service active, available RAM 13.47 GiB, disk 26.93 GiB, temperature maximum 38.0 °C, `usb_audio_present=false`. No microphone or NPU run; no production changes. See GitHub run #41809221114.

This strictly one-shot follow-up adds only a repository workflow scoped to `dev/ventuno-usb-alsa-metadata-20261104`. Hosted source/privacy/two-pass guard must succeed before a single self-hosted VENTUNO job starts. It fetches the exact commit into private temporary runner scratch and uses **only** audited read-only inventory sources:
- `scripts.ventuno_usb_audio_inventory.inventory_usb_audio()`: bounded `/proc/asound` metadata and `/dev/snd` character-device existence/access checks, never opens streams.
- `scripts.ventuno_alsa_capture_inventory.list_alsa_capture()`: lists metadata using `arecord -l/-L`, **not recording**; stdout remains unprinted except for numeric device pairs and boolean summary.
- `scripts.ventuno_usb_voice_dialog_readiness.inspect()`: safe fixed ALSA [1,0] route check and service status.

The output is **numeric card/device indices and booleans only**, with no raw device serials, ALSA labels, user data or raw failures. It identifies USB sound missing versus newly enumerated card indices versus Unix read/write permission blockage.

**Strict stop boundary:** This is *not* permission to record/play audio, activate voice, run model/NPU, restart services, install software, change group permissions or modify production. If the actual USB headset/microphone is disconnected, it must be physically checked by the operator before a separately consented one-shot voice test. No automatic reattempt, merge or deployment.
