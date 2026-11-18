# 2026-11-18 — Server-side one-turn MyAI ↔ Alma correlation

Source-only stacked DRAFT after PR #418. The operator requested that
MyAI's functionality be completed first; Alma V2 pronunciation training
is deferred. Working App Lab Alma V1, MyAI and GenieX are not touched.

## Implemented
- New \`core/app_lab_private_reply_server.py\`, disabled by default.
- Accepts ONLY an already-connected AF_UNIX stream with kernel-verified
  peer UID, strictly bounded receive timeout, canonical signed session
  request, expiry, one-use ID replay guard and host-owned Stop/session/
  ASR-release callbacks.
- Calls the existing \`AppLabFinalTextHandoff\` exactly once; its tool
  verifier never approves an unconsented effectful tool plan.
- Rejects automatic memory persistence before AND after dispatch.
- Binds a signed, length-prefixed, **redacted** answer to the exact
  authenticated request ID; uncertain/failed/blocked dispatch sends only
  a signed \`withheld\` reply, never raw answer content.
- A final check prevents sending a reply after host Stop or release loss.
- Returns only status codes (not raw transcript/answer) to caller.
- Full real Linux kernel AF_UNIX socketpair end-to-end tests with existing
  client in PR #418, fake MyAI core and no hardware.

## Not yet physically integrated
Neither socket listener nor accepted path/permissions, container mounts,
uid configuration, ephemeral keys, real microphone/ASR release, NPU/GenieX
arbitration, MyAI service lifecycle, real audio playback nor any
production profile edits are implemented. Host-provided callbacks are
NOT proof that hardware actually released its microphone. The one-use
replay guard is process-local; host restart/session rotation needs real
key provisioning and replay state discipline. No operator consent
for live rollout has been used.

## Validation gate
Hosted disposable ARM64 full repository CI must pass for exact PR
commit; do not merge or deploy this draft otherwise.
