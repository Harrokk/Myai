# App Lab → MyAI private Unix final-text transport: source-only design

Date: 2026-11-13. Status: DRAFT. **No running socket server, client, model connection, microphone, or deployment.**

## What is implemented

- core/app_lab_unix_final_text.py adds a strict 2048-byte framed request format using canonical UTF-8 JSON, a random per-session 32-byte HMAC key, exact field schema, and per-request 128-bit hex ID. HMAC-SHA256 binds the session, freshness timestamp, message ID, action and recognized final text. Raw words never appear in error messages or logs.
- A bounded in-memory replay guard refuses reused IDs without automatic eviction. A fresh high-entropy session ID and independently provisioned secret must be used for each new explicitly authorized operator session, including after restarts. A full ledger fails closed.
- Transport checks Linux kernel SO_PEERCRED with an independently configured positive UID and enforces AF_UNIX only, fixed frame limit and a bounded timeout. This reuses the existing vetted core/selfdev_unix_peercred.py function.
- The connector receives an **already connected** socket supplied by a future trusted owner; it does **not** create, bind, listen, accept, connect, mount a socket, expose HTTP/WebUI or create keys.
- Trusted caller callbacks (not wire fields) must say that the operator session is active and the ASR microphone is released; a Stop callback is checked before and after authentication and during MyAI tool dispatch.
- Only after those gates does it call the *disabled-by-default* one-shot core/app_lab_voice_handoff.py adapter, which never approves effectful tool plans.
- Reply remains a private Python return value. It is NOT transmitted to App Lab or TTS yet. TTS ownership and response framing remain open.

## Boundaries and unresolved risks

- A kernel UID is not enough to authenticate a container by itself, especially with user namespaces or other processes sharing a UID; require a unique principal/ACL and the private HMAC key. There is no key distribution implementation. **Never put the secret in source, CLI args, GitHub Actions environment, App Lab logs, or a publicly mounted folder.**
- The 30-second request-age tolerance relies on the same VENTUNO host wall clock and a fresh session ID; HMAC cannot prevent replay after a server restart if both the session ID and secret are reused. New sessions must rotate both.
- No end-to-end identity for the user's physical voice has been established. No pre-existing permission for recording is inherited. A future operator-owned client must validate a real ASR final event (or explicitly chosen partial fallback), ensure the physical microphone is released, and provide an authenticated/authorized local channel.
- The model-backed MyAICore can still write memory/audit/health files according to configured policy; **do not enable this interface live before reviewing memory-write and tool side effects**. The App Lab prototype's ASR/LLM/TTS resource lifetime, duplicate audio responses, speaker selection and concurrent NPU use are not yet coordinated.
- No cross-container Unix socket path or Docker mount exists in this commit. In particular the Unix socket path is NOT set to the running MyAI user home directory, no port is bound, and the App Lab container has not been modified.
- This source is not a drop-in hotpatch to the functioning Alma app. Do not deploy or merge without separate consent, pinning, review, and physical validation.

## Synthetic tests

tests/test_app_lab_unix_final_text.py verifies valid HMAC, wrong keys/sessions, expiration, strict JSON, tampering, malformed Unicode/control chars, duplicate fields, AF_UNIX/uid/timeout gates, truncation, replay concurrency, disabled default, trusted lifecycle checks, stop suppression and proof that no listening socket is created. Uses fake Unix peers; never opens physical audio.

Run on disposable hosted ARM64 via the existing dev/** workflow. No self-hosted VENTUNO workflow or live service is invoked.
