# STT child pipe failures and optional Linux resource policy

**Status:** DRAFT / source-only. No changes to running VENTUNO, GenieX, model, mic or service state. All resource caps are **off by default**, and require separately enabled isolated STT.

## Premature child pipe close

`core/voice_stt_bounded_io.py` now refuses a response if the worker closes its stdout while the parent still has unsent PCM. Even plausible valid JSON cannot count as a vote when the entire utterance was not transferred. Failed/closed stdin, fragmented JSON, deadline and excessive output remain fail-closed: the owned child process group is cleaned up, no transcript is dispatched.

Hosted Linux regression tests start disposable synthetic children that intentionally respond before reading a maximum-length 2 MiB PCM buffer, close stdout/stdin prematurely, or keep sleeping. They assert rejection and bounded completion. These are **not speech model tests**.

## Unprivileged experimental resource caps

| Voice setting | Default | Valid optional values | Linux child mechanism |
|---|---:|---|---|
| `stt_child_cpu_seconds` | `0` | `0` or integer 5–300 | `RLIMIT_CPU` CPU time |
| `stt_child_virtual_memory_mib` | `0` | `0` or integer 1024–8192 | `RLIMIT_AS` virtual address space |

When both values are zero, the worker does **not** change inherited OS limits. Nonzero caps are allowed only with `stt_process_isolation_enabled=true`. `core/voice_stt_child_limits.py` validates strict integer values (never boolean/string), passes fixed numeric values via an explicit minimal subprocess environment, and applies Linux/POSIX `resource.setrlimit` inside the actual Python STT **child**, before importing FasterWhisper/native libraries. It does not change MyAI, GenieX, the host/runner or systemd resources. If the parent sends invalid settings or the kernel refuses the limit, the worker fails rather than silently proceeding with weaker limits.

**Important limitations:**

- `RLIMIT_AS` limits **virtual address space**, not RAM resident set size (RSS). Native inference libraries may reserve large virtual mappings and fail even if actual physical RAM use would be safe. It is **not** a device-wide memory quota.
- `RLIMIT_CPU` covers CPU time, not wall time. The existing monitored IPC deadline still controls per-utterance wall-clock delay.
- Limits are per process, inherited by helpers but **not summed** across multiple independent helpers or STT providers. Group kill from PR #216 cannot guarantee cleanup of processes that leave the group. For reliable aggregate CPU/RAM containment, reviewed Linux cgroup v2 setup would be required; this has **not** been installed or enabled.
- No cgroup, privileged resource setting, OOM trigger, real Whisper benchmark or physical NPU test has been attempted on VENTUNO. The hosted synthetic child test demonstrates that a 1 GiB `RLIMIT_AS` rejects a new 2 GiB anonymous mapping without allocating that amount of physical RAM.
- Before any physical deployment, determine representative VENTUNO model virtual-memory mappings/RSS and concurrent GenieX headroom, then validate the chosen limits with the user present. These tests remain in `docs/PHYSICAL_PRESENCE_TESTS.md`.

## Safety verdict

Source-only and synthetic test evidence can establish input validation, subprocess-only limit application and failure behavior. It **cannot** establish safe physical thresholds for FasterWhisper/GenieX or guarantee recovery from uninterruptible native/kernel tasks. Keep both caps zero until such physical proof exists.
