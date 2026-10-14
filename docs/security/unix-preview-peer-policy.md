# Linux AF_UNIX peer identity — inspection-only security primitive

\`core/selfdev_peer_identity.py\` reads kernel \`SO_PEERCRED\` from a caller
supplied, **already connected AF_UNIX SOCK_STREAM socket**. It never opens,
listens, binds, connects, receives, sends or interprets a request. Arbitrary
JSON fields named \`uid\` or \`pid\` are not trusted.

Allowed runtime UIDs and the distinct updater UID are supplied from
out-of-band trusted configuration (frozenset of integer UIDs). A Linux
socket's kernel-reported runtime UID may pass the **preview-only** policy.
Every accepted result still has \`authorizes_mutation=False\` and
\`requires_human_approval=True\`. Root and updater accounts cannot be
members of the runtime allowlist.

Caveats:
- This is NOT a privileged updater daemon, actual authenticated IPC flow,
  anti-replay protocol, message framing, OS account migration or permission
  to sign, install or recover code.
- \`SO_PEERCRED\` describes peer credentials at connection establishment.
  A future implementation must accept newly connected clients, check the
  accepted socket, and not trust a socketpair created before a later fork/
  UID transition. It must combine peer identity with transport framing,
  manifest signature, independent permissions and bounded request policies.
- This functionality fails closed on Windows and other platforms lacking
  Linux \`SO_PEERCRED\`; no Windows equivalent is claimed.
- Unit tests use ephemeral local AF_UNIX socketpairs, never host services
  or production sockets.
