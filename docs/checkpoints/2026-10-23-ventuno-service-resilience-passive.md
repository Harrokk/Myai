# MyAI VENTUNO service resilience — passive remote check (2026-10-23)

Continued at DRAFT PR #369: safe hardware inventory succeeded with 8
CPUs, 48 sensors, 13.59 GiB RAM available, normal eMMC wear status and
one unblocked Bluetooth adapter. Real independent HTP use alongside
GenieX remains NO-GO.

The user is away from the device and requested continued progress.
This change adds **one bounded, strictly passive reliability preflight**
for the already-running services and host pressure; no reboots, simulated
crashes on the actual machine, service restarts, audio, camera, Bluetooth
I/O, network port probes, inference requests or file writes to production.

**Live read-only signals:** exact allowlisted systemd unit properties for
MyAI, GenieX and GitHub runner; restart-policy declaration and observed
`NRestarts`; optional cgroup v2 memory events, host CPU/memory/I/O
pressure-stall information (PSI), `MemAvailable`, root disk space and
inode headroom. Two snapshots several seconds apart detect changes
only within that bounded window and do **not** prove 72-hour uptime or
resilience to reboot/network loss. No raw journal, service environment,
command line, user path, token, process IDs, hardware identifiers,
SSID/IP/MAC or user content is exported.

Run independent pre-existing **mock-only tests** for GenieX supervisor,
health-based backend recovery, runner boot-policy classifier and the new
response sanitizer; these must not issue a live restart. The production
watchdog's actual safety mode is read as metadata, not changed.

`Restart=always` (or similar) documents a configured policy, not an
actual restart/recovery success. `NRestarts=0` is a counter since the
unit's current state lifetime, not a lifetime promise. If a property
is unavailable, report unknown. Cgroup v2 `memory.events` OOM counts
are optional and cannot be extrapolated to total host reliability.

The GitHub Actions self-hosted job is gated to one specific initial
push and exact commit transition; no `workflow_dispatch`, reruns or
further branches authorize a second board job. Code tested on a
disposable hosted ARM64 runner in existing full CI. Keep DRAFT; no
production deploy.
