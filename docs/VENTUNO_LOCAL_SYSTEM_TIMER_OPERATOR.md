# Ventuno Q: local terminal proof of independent systemd timer

**Status:** This is a manually run **synthetic canary**, not a live rollback
procedure. It does not pause GenieX or MyAI, change the GitHub runner, run
QNN/HTP, alter sudoers, or install persistent units.

## Why a local terminal is required

On 2026-10-15 the GitHub Actions runner confirmed that `sudo -n -l`
lists the systemd timer command as allowed, but actual `sudo -n
systemd-run --system ...` requires interactive authentication. Consequently,
a GitHub workflow must **never** attempt to provide or store a sudo
password. The previous `systemd-run --user` path was unavailable.

This entrypoint requires an actual interactive terminal (including a
proper SSH pseudo-TTY) on the Ventuno running as `arduino`. GitHub
Actions and non-interactive commands are rejected before sudo runs.

## Operator steps (only when at the board)

1. Verify that the draft [PR #207](https://github.com/Harrokk/Myai/pull/207)
   has been reviewed. Compare its **full head SHA** against the checkout
   obtained below; do not run arbitrary newer branch code without reviewing
   the diff. This work remains unmerged and does not replace `~/MyAI`.
2. Open a local shell/SSH TTY on Ventuno as `arduino` (not root). Ensure
   GenieX and MyAI remain running as usual.
3. Run these commands; they fetch and create a temporary **separate
   worktree**, not a production checkout:

```bash
set -euo pipefail
test "$(uname -m)" = aarch64
test "$(id -un)" = arduino
cd /home/arduino/MyAI
git fetch origin dev/ventuno-local-console-system-timer-canary-20261015
git rev-parse FETCH_HEAD
# Compare the printed full commit SHA to the reviewed PR #207 head.
# Continue ONLY if it matches the reviewed GitHub PR head.
umask 077
CANARY_DIR="$(mktemp -d "$HOME/myai-htp-console-canary.XXXXXX")"
git worktree add --detach "$CANARY_DIR" FETCH_HEAD
cd "$CANARY_DIR"
python3 -B -m scripts.ventuno_local_console_system_timer_canary \
    --local-terminal-only --fake-markers
```

The Python command prompts for local sudo authentication **only if it is
run in an interactive TTY**; no password is sent to ChatGPT, GitHub,
Actions, logs or configuration files. The sudo command targets only
`/usr/bin/systemd-run --system --on-active=5s`, which schedules a transient
one-shot service explicitly run as `arduino`. Its *only permitted action*
is writing a fixed fake `restored` marker under a private temporary
directory. It does **not** call `systemctl stop/start/restart`.

The report emits exactly one line with prefix
`MYAI_LOCAL_SYSTEM_TIMER_CANARY_JSON=`. The **only success status** is
`local_system_timer_restored_marker_after_controller_exit`. This means
the harmless system-manager timer ran after a disposable controller
process exited. Any `no_go_*` status is an unsuccessful proof, even when
unit tests or a GitHub job are green.

When the shell has returned, clean the separate worktree using your
actual `CANARY_DIR` from the **same shell**:

```bash
cd /home/arduino/MyAI
git worktree remove -- "$CANARY_DIR"
```

The script itself removes all temporary marker files. Do not remove
files created by another administrator. Do not run `sudo -v` inside
GitHub, add a blanket NOPASSWD policy or provide credentials in this
chat.

## Scope and remaining requirements

A positive manual canary demonstrates only that PID1's system timer can
perform a non-privileged callback after its initiating controller exits.
It **does not** demonstrate runner-disconnect survival, board reboot
recovery, hardened root lease arming, production service restoration, or
any direct NPU profiling. All such claims remain explicitly unverified.

The separate root-lease handler and systemd service/timer *templates*
in PR #205 are **not installed** by this test. Full deployment would
require independently reviewed permissions, out-of-band rollback,
failure injections on disposable units, and explicit live maintenance
authorization **before** any GenieX interruption.
