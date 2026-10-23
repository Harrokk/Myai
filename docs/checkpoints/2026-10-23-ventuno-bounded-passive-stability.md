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
