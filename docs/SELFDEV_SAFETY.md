# MyAI self-development safety model

Self-development support is prepared but disabled by default.

Current defaults:

```json
{
  "enabled": false,
  "workspace_root": "runtime/selfdev",
  "promotion_enabled": false,
  "require_bubblewrap": true,
  "verification_timeout_seconds": 300
}
```

No self-development function is exposed as a natural-language MyAI tool.

## Safety boundary

Candidate code is never written directly into the active project.

A session creates a separate staging copy under:

```text
runtime/selfdev/<session>/workspace/
```

Only selected text/source areas are copied:
- `core/`
- `modules/`
- `tests/`
- `scripts/`
- `config/`
- `docs/`
- `firmware/`
- selected root files such as `mail.py`, `MyAI_PROJECT_SPEC.md` and `requirements*.txt`

The staging layer rejects:
- absolute paths
- `..` traversal
- `.git`
- `runtime`
- virtual environments
- symlinks
- unsupported/binary file suffixes

## 1. Explicitly enable staging

Selfdev remains disabled until a human changes configuration.

Promotion is controlled separately and should remain disabled while only experimenting with staging.

## 2. Create a session

```bash
python3 scripts/selfdev_create.py --session experiment-001
```

This copies allowed project source into staging and records SHA-256 hashes of the active source baseline.

Active project files are not modified.

## 3. Modify only staging

Candidate edits belong under the session's `workspace/`.

Any write performed through the staging API invalidates an earlier verification result.

## 4. Review the exact diff

```bash
python3 scripts/selfdev_review.py experiment-001
```

Review reports:
- changed files
- added files
- deleted files
- source drift
- verification status
- unified text diff

The current implementation does not support promoting file deletions.

## 5. Verify inside Bubblewrap

```bash
python3 scripts/selfdev_verify.py experiment-001
```

Verification refuses to run if Bubblewrap is unavailable.

There is intentionally no fallback that runs generated tests/code directly on the host.

The verification sandbox:
- unshares namespaces
- has no network namespace access
- receives a minimal synthetic `/dev` rather than host hardware devices
- binds system libraries read-only
- binds only the staging workspace read/write
- uses a temporary HOME
- runs the fixed command `python -m pytest -q`

The verification record contains the exact staging manifest digest. Any later staging change invalidates or mismatches that verification.

## 6. Promotion requires a second explicit enable

Even a passing Bubblewrap verification cannot modify active code while:

```json
"promotion_enabled": false
```

After deliberate human review and explicit configuration enablement, promotion requires the exact phrase:

```text
PROMOTE <session-id>
```

Example:

```bash
python3 scripts/selfdev_promote.py experiment-001 \
  --approve "PROMOTE experiment-001"
```

Promotion is rejected if:
- selfdev/promotion is disabled
- verification is missing or failed
- verification was not Bubblewrap/network-isolated/device-isolated
- staging changed after verification
- active source changed after session creation
- a file deletion is present
- the approval phrase is not exact

Before touching active files, promotion creates rollback copies.

File replacement is atomic.

If application fails partway through, already-applied files are restored from the rollback backup.

## 7. Rollback is also explicit

A successful promotion receives a promotion ID.

Rollback requires the exact phrase:

```text
ROLLBACK <session-id> <promotion-id>
```

Example:

```bash
python3 scripts/selfdev_rollback.py experiment-001 promo-id \
  --approve "ROLLBACK experiment-001 promo-id"
```

Rollback checks that active files still have the hashes written by the promotion. If a human or another process has edited a promoted file afterward, automatic rollback refuses to overwrite that newer work.

Files added by the promotion are removed on rollback; modified files are restored from backup.

## What is intentionally not implemented

Selfdev currently does not:
- autonomously enable itself
- autonomously enable promotion
- expose staging/promotion/rollback as natural-language tools
- grant arbitrary shell access
- run candidate code directly on the host
- use network access during candidate verification
- expose host hardware to candidate tests
- delete active project files
- commit/push changes to Git automatically
- bypass manual review/approval

Future AI-generated candidate changes can be connected to this staging API, but the promotion boundary should remain externally controlled.
