# 2026-11-19 — Hosted real cross-UID App Lab ↔ MyAI test

This is a **source-only DRAFT**, stacked on PR #421. It never runs on
VENTUNO Q and it never touches installed Alma V1, GenieX, MyAI runtime,
memory database, microphone, speaker, hardware user IDs or services.

## What this test does

A dedicated GitHub-hosted **x86_64** workflow downloads an exact commit
into disposable private scratch and stages only the relevant public
source modules. It starts a pinned Python 3.12 Docker container with:
- networking off, root filesystem read-only, no-new-privileges;
- all capabilities dropped except narrowly scoped CHOWN, FOWNER,
  SETUID and SETGID, required for synthetic UID setup;
- memory/PID/CPU limits and volatile tmpfs; no VENTUNO hardware or
  private credentials mounted.

Inside this disposable container only, root sets up three distinct numeric
identities: server UID 23211, client UID 23212 and outsider UID 23213.
The server owns a private directory (0750) and binds its AF_UNIX socket
(0660) only AFTER dropping privileges. A dedicated group 23220 grants
the client access to that one IPC socket. The outsider has no group
membership and must be unable to connect or read either user's fake
private marker files. The client and server must also be unable to read
each other's private marker files.

The parent generates a new 32-byte HMAC secret and new 16-byte session
and request IDs, then passes short bootstrap data to each child via
anonymous pipes. Neither child is given arbitrary text, real model
objects, App Lab processes or filesystem secrets. Exactly one harmless
fixed Swedish synthetic utterance is used per scenario.

The exercise verifies (1) a valid cross-UID signed answer, (2) a
blocked response that is signed but withheld and (3) a deliberately
wrong secret that prevents any fake MyAI dispatch. Report output
contains only generic result metadata.

## What a PASS does not mean

This proves Linux UID and POSIX discretionary access control in
temporary, networkless Docker only. The real VENTUNO App Lab container
mount namespace, service unit ownership, key provisioning, session/Stop
authority, Whisper microphone release and GenieX/Qualcomm NPU resource
sharing remain unverified. It does not authorize deployment. All code
is disabled on the physical device; PR remains a DRAFT and unmerged.

Alma V2 Swedish pronunciation training remains deferred as requested.
