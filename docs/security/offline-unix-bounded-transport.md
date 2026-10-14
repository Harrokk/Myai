# Offline, bounded AF_UNIX inspection transport (NO production socket server)

This experimental module reads exactly **one** framed preview message from
a caller-supplied, **already connected** AF_UNIX stream. It never opens,
binds, listens, accepts, connects or sends any data. No production MyAI,
GenieX, key, updater service or user account is touched.

Rules:
1. Verify Linux kernel \`SO_PEERCRED\` and out-of-band runtime UID policy
   **before consuming any bytes**. Deny root/untrusted peer.
2. Use one monotonic absolute deadline (0 < seconds <= 5) across the
   complete 4-byte header, at most 40 KiB payload, and final EOF check.
3. Use \`select.select\` plus \`MSG_DONTWAIT\`: a timeout or peer disconnect
   fails closed; the receiver's socket blocking state is never modified.
4. Require the sender to perform \`shutdown(SHUT_WR)\` after one request.
   EOF is necessary to demonstrate that no other bytes followed the frame.
   Additional or delayed trailing bytes, concatenated frames and a sender
   that remains open cause rejection.
5. If transport succeeds, pass bytes to the existing offline inspection
   pipeline: kernel UID, signature against independently trusted public key,
   signed SHA-256 on caller-supplied bytes, and preview-only replay ledger.
6. Even an accepted result remains
   \`authorizes_mutation=False\` and \`requires_human_approval=True\`.

**Limitation:** This is a reader built for isolated socketpairs, not a
production IPC service. A real transport would need lifecycle management,
per-peer connection quotas, server-side filesystem socket permissions,
credential transition policy, response framing, audit gating and DOS
controls. The EOF requirement intentionally forbids a persistent multi-
request connection. Half-close still permits a future reply in principle,
but this test prototype sends none.

The only possible intentional filesystem write during an authorized
preview is to the separately provided **preview-only test SQLite ledger**,
never to source files or a system updater.
