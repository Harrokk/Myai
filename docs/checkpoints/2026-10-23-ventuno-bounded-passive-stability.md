# VENTUNO Q — bounded passive multi-sample stability (2026-10-23)

Continuation of DRAFT PR #370. The user is away from the hardware and
requested to continue with harmless remote hardware/reliability checks.

**Scope:** precisely seven snapshots with 20 s between, approximately
two minutes of existing host telemetry. Reuse existing audited source
`scripts.ventuno_service_resilience_readonly.snapshot()` and
`scripts.ventuno_readonly_probe.temperature()`. Do not create a new
monitoring daemon, schedule future runs, connect a live model, or modify
any services.

Capture only already available systemd unit status and start metadata,
memory availability, disk and inode headroom, CPU/memory/I/O PSI,
systemd cgroup OOM counts and max of published thermal sensors.

**Live job authorization:** single exact push of one workflow file on a
single review branch, tied to a unique predecessor commit SHA and commit
message. No manual dispatch, further pushes or rerun permission.
Read-only normal-user Actions runner; temp source checkout deleted when
the workflow finishes.

Privacy and safety: never export environment variables, process command
lines, journals, network addresses, radio names, credentials, service
paths, individual per-sensor paths or raw telemetry blobs. No audio,
camera, Bluetooth scans, physical input/output, service restarts,
fault injection, thermal stress, storage write benchmark, NPU model,
WebUI or other production changes.

A clean outcome means **no service restart observed over only those
seven metadata samples**; it is not evidence of true fault recovery,
multi-day operation, a reboot test, or absence of all possible errors.
A service can fail and recover between samples. Unreadable metrics are
unknown, not zero, and should downgrade the result as appropriate.

The existing runner systemd Restart=no finding remains a known
unresolved risk; do not apply the already staged systemd drop-in until
the user is at the board and independent recovery is available.

## Verified real VENTUNO execution

**Run:** https://github.com/Harrokk/Myai/actions/runs/39988701997
**Frozen source SHA:** `7dfe00f39b8fe8f38830f5de8aef3e29ec52a609`
**Actions status:** SUCCESS.
**Regression:** 41 selected fake-fixture/read-only source tests passed.

**Seven real snapshots** completed over **120.1 s**, using
existing passive systemd, cgroup, proc, thermal and PSI collectors.
Sanitized measurements:

| Metric | Observed |
|---|---|
| MyAI, GenieX and GitHub runner | All active at every sampled point |
| Process service identity and restart counter | No change in any of the three |
| OOM kills delta (MyAI, GenieX) | 0, 0 |
| Maximum thermal sensor value | 38.1 °C |
| Minimum MemAvailable | 13.61 GiB |
| Minimum free root storage | 27.95 GiB |
| Minimum free root inodes | 90.75% |
| CPU pressure some avg10 maximum | 0.18% |
| Memory pressure some avg10 maximum | 0.0% |
| I/O pressure some avg10 maximum | 0.0% |

Status is `no-service-disruption-observed-in-bounded-window`.
Both MyAI and GenieX still have a configured systemd restart policy.
Runner still has `Restart=no` (though loaded/active/boot-enabled);
the prepared drop-in **was not installed**. There was no production
service change, fault injection or model, audio, camera, Bluetooth or
network active test.

**Limits:** these seven point samples cannot establish continuous
uptime between readings. No actual failure, recovery, reboot, power
interruption, thermal stress, multi-hour duration or NPU inference
was attempted. No real-world ASR test occurred because the user
is away from VENTUNO.

Further steps should not repeat passive telemetry indefinitely:
the remaining meaningful gates are controlled fault/reboot recovery,
Bluetooth link/voice I/O and QNN/GenieX concurrency. Those require
specific fresh approval and an operator with out-of-band access.
