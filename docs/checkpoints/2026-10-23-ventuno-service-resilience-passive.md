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

## Real VENTUNO results: 2026-10-23

**Actual once-only board job:** https://github.com/Harrokk/Myai/actions/runs/39976536805
**Code SHA:** `212d8200a90470a6be97fca55f6e289dab43558c`
**Conclusion:** SUCCESS. 27 targeted fake/mock recovery and validator
tests passed; two passive real-board snapshots over ~4 seconds.

- `myai-ventuno.service`: loaded, active in both snapshots,
  `UnitFileState=enabled`, systemd restart policy **configured**,
  `NRestarts=0`, unchanged `ExecMainStartTimestampMonotonic`,
  last unit `Result=success`.
- `myai-geniex.service`: same observations, restart policy configured,
  zero counted restarts and no process start change in observation.
- `actions.runner.Harrokk-Myai.ventuno-q.service`: **loaded, active,
  enabled-on-boot, but systemd `Restart=no`**. Zero counted restarts
  and stable main process during observation.
- `/sys/fs/cgroup/system.slice/*/memory.events` where readable:
  both MyAI and GenieX observed **zero `oom_kill`** and zero
  `memory.high` count change during the short check.
- Host PSI 10-second `some` pressure: CPU **0.26%**,
  memory **0.00%**, IO **0.00%** at second snapshot.
- Host memory available **13.59 GiB**, root filesystem available
  **27.95 GiB**, root free inode headroom **90.75%**.

**Important operational finding:** GitHub runner's systemd unit will
be enabled at boot, but **systemd will not auto-restart it after a
service process exit** while the system stays up. This can strand
unattended GitHub management until an out-of-band login or reboot.
Prior project work already staged
`deploy/systemd/actions.runner.Harrokk-Myai.ventuno-q.service.d/20-myai-restart-policy.conf`
containing `Restart=always`, `RestartSec=15s` and a
5-per-300s start rate limit. **It is explicitly REVIEW ONLY and
was never installed. DO NOT install or reload services unattended.**

## Provisional remediation — preparation only

1. When an operator is present with reliable independent console
   access, inspect installed runner vendor unit and confirm service
   path, ownership, update semantics and effective `Restart=no`.
2. Verify an out-of-band recovery path that does not depend on the
   GitHub runner being online. Back up vendor unit and existing
   drop-in directory with correct permissions.
3. Review the existing **unapplied** drop-in; apply only after
   a separate specific operator approval, then validate systemd
   config. Do not deploy a replacement vendor unit. Plan for loss
   of GitHub access on a bad setting.
4. Recheck runner active/ready status and `NRestarts`. A genuine
   restart/failure injection or reboot requires its own approval,
   especially as it can strand remote access.
5. On regression, restore the previous drop-in configuration via
   local out-of-band console, reload systemd and verify service
   recovery. Never depend on the affected runner to perform rollback.

This exercise **did not** verify unattended failover, reboot recovery,
a 72-hour stability test, or external network outages. It did
confirm live service activity, current restart-policy declarations,
short-window stability and the safety of mock-only recovery policy
tests. No production service, audio, inference or config was changed.
