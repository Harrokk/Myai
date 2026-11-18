# 2026-11-18 — Two-process temporary private App Lab/MyAI rehearsal

Stacked after PR #420. Source-only DRAFT; NEVER deploy this test harness
as a service on VENTUNO. This is progress toward isolated real processes,
not a production App Lab integration.

## Host-only, single synthetic utterance

\`core.app_lab_private_process_rehearsal.rehearse_two_private_processes\`
requires \`enabled=True\`. It creates a 0700 non-root owned temporary
directory and one 0600 filesystem AF_UNIX socket, then launches TWO
independent Python processes using the checked-in fixed roles.

A fresh 32-byte HMAC secret and independent 16-byte session/request IDs
are generated in parent RAM for each rehearsal. Parent injects exactly
72 bootstrap bytes into each child using two distinct inherited anonymous
pipe FDs (\`subprocess.pass_fds\`), **not** subprocess command lines,
environment variables, disk, network or GitHub logs. The server inherited
socket listener FD is already bound by the trusted parent. The client
connects only to this temporary owner-private path. Linux peer UID and
signed request/session/reply are checked by existing PR #418–419 modules.

Neither child may accept arbitrary user text, actual MyAI, provider,
external command or model. It uses a hardcoded synthetic Swedish question
and fake read-only MyAI answer. Blocked/uncertain outcomes are signed
and withheld. A mismatched secret prevents any fake dispatch. Parent
collects only status JSON, cleans process children/FDs/socket/temporary
directory before returning. Default is completely disabled.

The runner uses the SAME non-root UID in both processes. This demonstrates
real process separation, safe in-memory secret FD injection and private
kernel Unix-socket transport. It does **not** demonstrate cross-UID ACL,
App Lab Docker namespace access, host service isolation, physically
verified microphone shutdown, stop-signal wiring, GenieX concurrency,
or live VENTUNO TTS. All earlier PRs remain unmerged.

## Next required gates

- Securely provision separate operator-controlled UIDs or equivalent
  kernel isolation with deliberate exact cross-boundary privileges.
- Audit approved AF_UNIX path ownership / mount layout across real
  App Lab runtime and MyAI service.
- Integrate a real lifecycle authority for physical consent, microphone
  release, current Stop state and fail-closed cancellation.
- Coordinate QNN/GenieX, Whisper and Piper model/resource ownership.
- Only then prepare an explicitly authorized single hardware smoke test.
