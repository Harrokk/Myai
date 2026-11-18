# 2026-11-18 — private connected App Lab request/reply client

Stacked after PR #417; **source-only DRAFT**, no activation.

This stage adds a Python client that can send a signed first **full_text**
utterance over an ALREADY CONNECTED, private Linux AF_UNIX stream and
receive a single authenticated answer, without a real Arduino runtime.

The caller (not this module) must:
1. Confirm the actual operator-owned App Lab session, microphone capture
   shutdown and ASR release; \`session_active\`/\`asr_released\` callbacks are
   cooperative assertions, not hardware proof.
2. Extract final text through \`AlmaFinalASRGate.take_final\` (never an
   unreliable \`partial_text\` fallback for tool dispatch).
3. Provision fresh 32-byte secret/session/request IDs over a trusted
   mechanism, private socket path and mounted namespace. This PR does NOT.
4. Supply an already connected socket to a separately authenticated server
   under a pinned non-root Linux UID; client verifies SO_PEERCRED.
5. Monitor the session Stop signal during the reply wait; check once more
   immediately before ANY future TTS. Revoking consent after transmitting
   cannot undo actions already started on a remote host; the server still
   requires independent stop/risk policy checks.

The client sends exactly the existing canonical request frame and accepts
only \`private_reply.verify_signed_reply\` matching the outstanding request
ID, active session, signed HMAC, replay guard and response freshness. Reply
payloads remain in process memory. Never print raw text to logs.

The implementation does not create a socket, start a listener, launch a
service, run ASR/LLM/TTS, select an output device, write audio or install
anything. It defaults to disabled. Synthetic Linux kernel \`socketpair\`
tests exercise real send/receive, wrong peer identity, authentication,
status withholding, tampering, replay, Stop and bounded timeouts.

**Remaining:** a real trusted server that correlates the authenticated
request ID to MyAICore's result, private key/session provisioning, actual
host UID/socket mount, physical microphone/NPU arbitration, reviewed memory
policy, consented hardware smoke test. No deployment is authorized.
