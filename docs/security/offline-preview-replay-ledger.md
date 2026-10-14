# Offline inspection replay ledger (NOT an approval service)

This experimental component \`core/selfdev_preview_ledger.py\` allows
cooperating, isolated test processes to record **preview** request IDs once,
using SQLite's \`BEGIN IMMEDIATE\` and unique key constraints. It does not
authorize, sign, execute, merge, recover or deploy code.

- Uses a private SQLite file and refuses preexisting symlinks, hardlinks,
  unsafe permissions and broken databases.
- Retains request IDs rather than automatically pruning expired ones. A
  repeated ID stays rejected after expiration, even after restarting a
  process. Growth/capacity planning is still needed for production.
- Detects ID reuse with a different request fingerprint and refuses claims
  whose syntactic expiry has elapsed.
- Every result has \`authorizes_mutation=False\`. A recorded preview request
  is **not** human approval, signed source provenance, or a verified
  deployment artifact.
- This is tested only in disposable pytest SQLite databases, including
  independent worker processes. It is not wired into active MyAI,
  \`SelfDevPromotionManager\`, recovery or any update service.
- A same-UID attacker can still modify the SQLite file or its parent
  directory between checks. There is no real privilege separation or
  independently authenticated transport.
- A future privileged updater needs protected OS identity/ownership,
  approval verification with anti-replay *separate from preview requests*,
  safe database location, audit gating, artifact signature verification and
  a staged release design before any actual update can run.

The SQLite ledger is a **test prototype for admission replay behavior** only.
Do not use it as a root of trust or a reason to enable selfdev promotion.
