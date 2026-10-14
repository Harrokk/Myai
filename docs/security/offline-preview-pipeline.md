# Offline preview composition — NOT a privileged IPC implementation

\`core/selfdev_offline_preview_pipeline.py\` composes four distinct
inspection-only controls on caller-supplied test inputs:

1. A separately supplied, already connected Linux AF_UNIX socket's kernel
   \`SO_PEERCRED\` UID must match an out-of-band configured runtime UID.
2. A length-prefixed signed manifest must be **one** bounded frame, not
   truncated, concatenated or oversized.
3. An Ed25519 signature must validate against an **independently trusted**
   public key, and its payload must be a valid inspect-only manifest.
   Caller-supplied bytes must match the signed SHA-256 manifest.
4. A caller-supplied preview-only SQLite ledger records accepted preview
   request IDs exactly once across cooperating processes.

The result always says \`authorizes_mutation=False\` and
\`requires_human_approval=True\`, even when the preview is recorded.
No installer/updater call, service restart, release publication, code
execution, filesystem source scan, socket binding or listener is present.

**Not a secure deployment channel:** This does NOT authenticate a privileged
deployment approval, verify release provenance, ensure durability across
physical power loss, install users/services, or provide secure message
framing across an actual network transport. The framing functions operate
on in-memory bytes; a future transport implementation must additionally
defend against slow/partial reads, peer disconnects, credential transitions,
untrusted keyring provisioning and resource exhaustion.

A positive inspection result is *not* evidence of deployment authorization.
The only intentional filesystem mutation is to an explicitly provided
**test/prototype preview ledger**, never production MyAI code.
