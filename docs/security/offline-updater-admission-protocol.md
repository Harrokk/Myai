# Offline updater admission protocol (NOT a privileged updater)

**Scope:** Security prototype only; no server, socket, shell invocation, file
mutation, privileged OS users, Git fetch, deployment or service restart.

The pure module \`core/selfdev_request_protocol.py\` accepts a bounded JSON
\`bytes\` message describing an **inspection-only** candidate revision and up
to 32 canonical allowlisted source paths with SHA-256 hashes. It rejects
unknown fields, duplicate JSON object keys, Unicode/absolute/path-traversal
escapes, ambiguous casefold filenames, noncanonical file ordering, stale
requests and mutating actions. Accepted requests explicitly carry
\`authorizes_mutation=False\` and \`requires_human_approval=True\`.
\`compare_supplied_bytes\` only checks caller-supplied in-memory bytes and
returns a status of \`bytes_match_untrusted\` or a blocked status. It does not
open a source tree or assert a Git signature, release provenance, authorization
or readiness to deploy.

Example protocol:
\`\`\`json
{
  "version": 1,
  "action": "inspect_candidate",
  "request_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "revision": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "expires_unix": 1800000060,
  "files": [
    {"path": "core/example.py", "sha256": "770e607624d689265ca6c44884d0807d9b054d23c7f589b00985e0329a34b35"}
  ]
}
\`\`\`

## Explicit limitations and next security gates

1. **No transport authentication.** The request ID and SHA digest are labels,
   not a signature or authorization. Any connected runtime could fabricate
   them. Replay protection across requests and processes is not implemented.
   A future privileged updater must authenticate peer UID credentials and/or
   independently signed approvals, maintain a durable anti-replay ledger and
   independently fetch/verify the pinned source and artifact provenance.
2. **No filesystem-boundary implementation.** Accepted paths are syntax-only;
   a future updater must check real inodes, permission separation, source
   provenance, multi-file atomic release, and mandatory audit independently.
3. **No privilege separation tested** on the shared VENTUNO runner. Dedicated
   accounts, systemd migration, key rotation and actual publication remain
   **design only** in \`docs/security/selfdev-privilege-isolation-proposal.md\`.
4. **No physical tests, merges or deployments.** Selfdev promotion stays
   disabled; cleanup of historical GitHub server-side cache remains blocked
   pending independent GitHub Support confirmation (PR #110).

The module is deliberately not wired to \`SelfDevPromotionManager\`: passing
this parser cannot trigger an update. It is useful for offline adversarial
tests only and must not be mistaken for a secure updater service.
