# MyAI selfdev verifier process-output review (2026-10-18)

**Base:** DRAFT PR #322, exact source commit `ba2db3e63f293ef0778d9fe56e6b03172fa5e15e`. No merge to `main`, no installed VENTUNO change, no live self-modification.

## Pass 1 – confirmed resource-exhaustion finding

`SelfDevVerifier._default_runner` previously used `subprocess.run(..., capture_output=True, text=True)`. That buffers both child output streams in the **host Python process**. `max_output_chars` only truncated strings after the subprocess had finished. A staged test that wrote unbounded output could exhaust host RAM before the verifier returned a failure. A command timeout alone does not bound how many bytes can be emitted before expiry.

The sandboxed command is untrusted even when it has no network and a read-only staged directory. The host verifier must not trust its output volume.

## Pass 2 – isolated fix

- New `core/selfdev_bounded_runner.py` launches commands without a shell using `subprocess.Popen`, `stdin=DEVNULL`, separately piped `stdout` and `stderr`, and a sanitized environment supplied by the verifier.
- Drain both pipes incrementally with selectors. **Combined output is capped at 1 MiB per check.** If the limit is exceeded, fail closed. No unbounded in-memory pipe collection or disk-spooling fallback.
- Enforce a monotonic wall-clock deadline. On timeout, overflow or exceptions, kill the spawned POSIX process group and reap the direct child. Successful bounded runs preserve separate stdout and stderr in a `CompletedProcess`-compatible result.
- The verifier still records a failed check for an exception, revokes stale approvals before commands, keeps the shared promotion lock, and caps the stored transcript.
- New regressions exercise environment isolation on a real subprocess, ordinary streams, excessive stdout/stderr and a timeout. Synthetic local isolated execution also exercised normal output, overflow and timeout.

## Boundaries and explicit NO-GO

This limits **captured verifier process output**, not all resource use of untrusted tests (CPU, memory within child, fork bombs, host file permissions). Child groups that deliberately detach cannot be treated as fully isolated solely through process groups; rely on Bubblewrap and independent OS privilege separation for production. Even full CI success cannot authenticate a complete `verification.json` against a same-UID writer. Real on-device Bubblewrap tests, distinct untrusted verifier UID, full supply-chain/SBOM/license and native ABI review, power-loss recovery, physical voice and NPU remain open.

Require complete exact-HEAD GitHub-hosted ARM64 source-only CI. Draft only; no release authorization.
