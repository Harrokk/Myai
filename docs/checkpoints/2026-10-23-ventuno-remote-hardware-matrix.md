# Unattended VENTUNO Q hardware metadata campaign — 2026-10-23

## Operator scope
User is **not physically present** with VENTUNO and has requested
**other hardware tests**. We must not run microphone/audio capture,
speaker playback, cameras, Bluetooth discovery/pairing, active Wi-Fi
scans, model/accelerator inference, high-load stress tests, storage
benchmarking/writes, service restarts or unattended production changes.

### Tests performed
- Real-board two-pass metadata of CPU core count/current clocks, thermal
  sensor range, RAM, swap and root eMMC free space.
- USB device/interface count, ALSA capture/playback *capabilities* via
  `/sys`, `/proc/asound` and `/dev` metadata without opening.
- Wi-Fi/Ethernet interface link state and Bluetooth HCI presence
  without network traffic, SSIDs, MAC addresses or pairing.
- GPU and FastRPC/NPU *indicators* only; do not claim NPU performance,
  QNN support or safe parallel HTP inference based on these.
- Active `myai-ventuno.service` / `myai-geniex.service` status before
  and after, plus coarse boot uptime. Two snapshots 3 seconds apart
  are **not** a sustained thermal/stability or performance test.
- Existing guarded V75 NPU metadata gate
  `scripts.ventuno_v75_npu_readiness_readonly`: always NO-GO for
  live NPU inference, with no DSP or device opens.

Existing audited code is reused from
`scripts/ventuno_readonly_probe.py`,
`scripts/ventuno_remote_idle_baseline.py` and
`scripts/ventuno_v75_npu_readiness_readonly.py`. A small new summary
aggregator intentionally emits only bounded safe fields and clear
uncertainty. No device ID, IP, physical location, raw sysfs paths,
logs, tokens, process arguments, Bluetooth names or user data exported.

### Safety
One-use push workflow locked to exact prior commit and unique message;
self-hosted runner `arduino` only; isolated temporary source checkout,
no production deploy; no sudo. `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONNOUSERSITE=1`, pytest cache disabled, temp checkout deleted
if the runner finishes. Service state is verified on both sides.
Missing readings stay unknown; do not fake zeros or a green stress score.

### Distinction
This tests **sensor enumeration/readability and reported idle status**.
It does not establish physical microphone functionality with Whisper,
TTS, camera/video capture, Bluetooth link pairing, Wi-Fi data throughput,
storage read/write throughput or wear, NPU operator execution, DSP
model timing, or power stability under load.

No physical audio without separate fresh consent with the user present.
