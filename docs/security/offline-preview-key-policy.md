# Offline trusted preview-signing key lifecycle policy

This is an **in-memory policy only** for \`inspect_candidate\` messages.
\`PreviewSignerPolicy\` records describe a key ID, exact Ed25519 public-key
bytes, activation time, expiration time and an unconditional revocation flag.

\`active_preview_public_keys()\` only returns keys if each public key matches
an *independently pinned* SHA-256 fingerprint associated with its ID.
The record IDs must match the pinned ID set exactly, preventing unexpected,
missing or re-used public keys. Duplicate IDs or reusing the same public
key under another ID is refused. Time windows use \`start <= now < end\`.
Revoked keys never become valid again merely by rewinding the supplied
clock, and a policy with zero active keys fails closed.

An overlap between old/new active keys permits a deliberate **inspection**
rotation. Changing the pins, revoking an old key and updating the validity
windows must come from an authenticated out-of-band administrative channel,
**not from a signed manifest or runtime-provided payload**.

The verifier integrates with the existing **inspection-only** Ed25519
module and still never returns a deployment grant or changes source code.

Critical unimplemented guarantees:
- There is NO independent root-of-trust provisioning mechanism or signed
  administrative policy. The caller is assumed to provide trusted records
  and separately pinned fingerprints. If a same-UID attacker can replace
  both, the policy provides no protection.
- There is NO monotonic trusted clock/anti-rollback state across reboots,
  actual credential revocation distribution, role delegation,
  human deployment authorization or production key storage.
- Expired/revoked keys can still appear in old signed objects, but no
  preview is authorized through them under current time/policy.
- Real signer keys are **not** generated or installed on VENTUNO.
  Ephemeral private keys exist only inside hosted unit-test processes.
- No live selfdev promotion, IPC service or installation is connected.
