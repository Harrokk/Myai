# Ed25519 signed preview manifests: inspection-only verification

This draft adds \`core/selfdev_signed_manifest.py\`. Its **only** role is
verifying signatures over canonical JSON manifests that conform to the
existing \`inspect_candidate\` schema. It can never merge, install, recover,
promote, execute code, restart services or authorize access.

The signing input is canonical ASCII JSON with keys \`context\`,
\`algorithm\`, \`key_id\`, \`payload\`, and \`version\`; the
context is fixed to \`myai:inspection-only:ed25519:v1\`. The outer envelope
contains exactly \`version=1\`, \`algorithm=Ed25519\`, a signer key ID,
the inspection payload, and a canonical Base64-encoded 64-byte signature.

The verifier takes its trusted 32-byte Ed25519 **public** key mapping as
an independent *in-memory argument*. It **never** accepts a signing key
from the manifest itself, accesses a private key, loads keys from disk or
creates an updater service. An unknown signer, bad signature, invalid
payload, noncanonical Base64 or unavailable cryptography library is refused.
The result carries \`authorizes_mutation=False\` and
\`requires_human_approval=True\` even with a valid signature.

A valid Ed25519 signature proves only that the manifest was signed by the
holder of a corresponding trusted private key. This prototype does not
establish supply-chain source provenance, the identity/approval of a human
operator, safety of code bytes, anti-replay of privileged approvals, nor any
atomic deployment guarantees.

On VENTUNO the optional \`cryptography\` backend may be unavailable:
fail-closed is intentional. A separate **hosted x86 Linux test** installs
a pinned cryptography package and exercises real in-memory Ed25519 keys and
tamper verification. No cryptographic secrets or public keys are generated
or installed on the user's board. The private key in tests is ephemeral.

Do not wire this to \`SelfDevPromotionManager\` or treat preview verification
as permission to modify user files.
