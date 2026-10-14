# Disposable POSIX privilege test — NOT a Ventuno deployment

This workflow is intentionally limited to an **ephemeral GitHub-hosted Ubuntu
runner**, which starts a disposable Docker container with **network disabled,
root filesystem read-only, /tmp mounted as volatile tmpfs, and just one
test script mounted read-only**. No host or VENTUNO accounts, services,
keys or source trees are created or changed.

The script explicitly refuses execution when its Docker marker and
\`MYAI_DISPOSABLE_UID_TEST=yes\` gate are missing. Inside Docker, it uses
\`os.fork\` and \`setgid/setuid\` to simulate two distinct numeric UIDs:
\`23002\` (runtime) and \`23001\` (updater).

The tests exercise kernel-enforced file permissions:
- Runtime can read world-readable program code but **cannot** write that
  code, add source files, access updater-only staged content, read a fake
  signing key, or read/forge updater-only audit logs.
- The updater identity can read the **fake test-only** key, write test-only
  staging, add release content and append a private log.
- Real MyAI uses no these UIDs; no key or account from the device is read.
- A successful test validates a **permission-matrix concept only**.
  It does not implement privileged IPC, deploy code, verify artifact
  provenance, model all Linux capabilities or test real service identity
  migration. Actual Ventuno deployment would still need explicit
  authorization and separate physical validation.

Docker image note: the public \`python:3.12-slim-bookworm\` tag is
version-family pinned but **not digest pinned** in this initial simulation.
Before treating this workflow as a release gate, pin and independently review
a trusted immutable image digest. The job has no secrets or network access
inside the running container and does not mount the project root.

This is a short-lived CI demonstration, not an authorization to change
production system users, systemd units, MyAI voice services or auto-promotion.
