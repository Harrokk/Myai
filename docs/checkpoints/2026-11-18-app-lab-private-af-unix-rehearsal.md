# 2026-11-18 — Private AF_UNIX filesystem socket rehearsal

Stacked after PR #419; source-only DRAFT. This adds a **synthetic, entirely
off-device** one-turn rehearsal of the new authenticated App Lab↔MyAI
handoff, with actual Linux filesystem socket creation/bind/listen/connect.

The \`rehearse_one_private_turn(enabled=True)\` fixture:
- requires non-root Linux and a disposable, private \`tempfile.TemporaryDirectory\`
  (0700, owned by the test UID);
- binds a socket under that directory, sets mode 0600, confirms socket inode
  and owner, and accepts exactly one connection;
- generates fresh 32-byte HMAC secret plus independent 128-bit session/request
  IDs with the OS CSPRNG, **only in memory**; never creates token/key files;
- signs a single FIXED synthetic Swedish transcript and verifies peer
  credentials, freshness, HMAC, request ID and replay logic;
- invokes only hard-coded synthetic fake MyAI, which rejects write plans
  and has automatic memory persistence disabled;
- signs the response and checks authenticated return through the existing
  PR #418 client and PR #419 server;
- tears down socket, folder, descriptors and worker thread when finished.

Modes \`ready\`, \`blocked\`, and \`uncertain\` exercise permitted and withheld
synthetic replies. Default is disabled (zero I/O). The fixture cannot take
an arbitrary MyAI core or real user utterance. No production settings or
device profiles are changed.

### Still required for production
Separate genuine Linux service UID/ACL boundary and container namespace,
a trustable key-sharing mechanism between DIFFERENT processes, operator
consent and Stop wiring, physical ASR/microphone release evidence, NPU
resource arbitration, service lifecycle, MyAI process startup, and a
consented VENTUNO smoke test. The same-UID loopback test proves only
kernel socket transport in a disposable hosted CI process, not isolation
between two deployed services. Never interpret PASS as deployment approval.
