# 2026-11-13 — Authenticated private return contract for App Lab Alma

Source-only DRAFT, stacked on PR #415. The user has confirmed that the original
App Lab ZIP with Qwen, ASR and Alma speaks Swedish successfully on VENTUNO.
No new physical recording or VENTUNO deployment was authorized or performed.

## What this adds

A *portable* pure-Python module:
integrations/arduino_app_lab/alma_reference/private_reply.py

- Distinct reply HMAC-SHA256 domain (request and response signatures cannot
  be reflected or treated as each other), same 32-byte per-session secret.
- Canonical, strict, bounded JSON with session_id, request_id, completion
  timestamp, status, optional answer, and MAC.
- Reply requires a matching pending request ID and active session ID, expires
  after 60 seconds and rejects reply timestamps more than two seconds ahead.
- Reply ledger accepts each request's answer at most once, fails closed at
  its configured capacity, and must be replaced on a fresh session.
- A Stop callback must report exactly false before and after authentication.
  A further stop check is required before any future physical playback.
- Unsafe MyAI handoff outcomes (blocked tool dispatch, unknown/partial
  execution, manual review, invalid or oversized TTS text) are signed as
  'withheld' and never carry raw answer text.
- Returns only private in-process parsed data; signed frames can be
  length-prefixed and decoded purely in memory. No use of sockets, audio
  devices, file writes, logs, temp WAVs, web endpoints or credentials.
- 29 mock/synthetic tests cover tampering, bad JSON, duplicate fields, replay,
  concurrency, wrong request/session/secret, cancellation, withheld output,
  framing and non-ASCII text.

## What remains

The protocol is NOT yet an active bidirectional bridge. There is no server,
app client, key provisioning, container bind mount, authenticated peer
connect, sound device handoff, model resource scheduling or actual playback.
The actual App Lab ZIP has a speaker command that operates separately and
must remain untouched until the operator approves a controlled new app.

Before live activation, re-review the *host* memory/health/audit policy and
real operating-system socket permissions; the source-only bridge does not
authenticate the speaker or guarantee that the microphone is physically
closed. Never expose the MyAI return text to App Lab WebUI's public broadcast.

Source file and tests are free of audio or third-party dependencies. Verify
exact-head hosted ARM64 CI before marking this PR ready for review. Do not
merge or deploy this draft without explicit user action.
