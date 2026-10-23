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

## Measured result on actual VENTUNO Q

**Run:** https://github.com/Harrokk/Myai/actions/runs/39973069454
**Run source SHA:** `cac9749bfb417638a7c1e83ec41d4024c91bbc11`
**Outcome:** GitHub Actions SUCCESS. **33 targeted synthetic tests passed**,
then two direct live hardware metadata reads and existing safe NPU
preflight completed. Production MyAI and GenieX active on both snapshots,
verified independently by systemctl before and after.

Observed second-snapshot values unless otherwise stated:

| Probe | Actual observation |
|---|---|
| CPU | 8 logical cores, sampled 8 current frequencies; 845–1344 MHz |
| Thermal | 48 valid sysfs zones; maximum 39.2 °C first, 38.5 °C second |
| RAM | 14.93 GiB total, 13.59 GiB available, 0 GiB swap |
| Root storage | 54.9 GiB total, 27.95 GiB available |
| USB | 4 physical USB devices; 1 USB audio card |
| ALSA | 2 capture PCM, 3 playback PCM — **not** audio functionality tests |
| Network | 1 Wi-Fi interface and 1 up link; 1 Ethernet interface |
| Bluetooth | 1 HCI controller visible; **not** link/pairing verified |
| GPU | 1 render node |
| NPU/RPC | 5 FastRPC nodes; 3 remote processors running; QNN HTP library found in standard paths |
| Service status | MyAI and GenieX active before and after |

The *existing* read-only QAIRT V75 NPU compatibility classifier
returned `no_go` despite vendor runtime packages and secure device
metadata being present. Specific blockers:
`htp_v75_operator_support_unverified`,
`active_geniex_concurrency_unsafe`, and
`vendor_htp_placement_proof_not_available`. This does not mean the
built-in Arduino model is incompatible; it means a separate unmanaged
QNN/HTP run is not safely proven alongside the current GenieX.
No QNN or HTP execution attempted.

The 3-second thermal delta (-0.7 °C for the maximum among readable
zones) is **not** a cooling benchmark or throttle check. No
long-duration CPU stress or storage benchmark was permitted. USB audio
card existence is not confirmation of physical recordings. Network
interface link-up is not throughput proof. NPU nodes and host libs
are not proof of inference speed.

**Next optional unattended metadata tests**: persistent eMMC wear
attributes if exposed by the board, CPU thermal throttle counters
if supported by the kernel, Bluetooth rfkill state; no camera/audio
activation, network scan or model run. Physical ASR remains deferred
until user returns.
