# Git history cleanup for historical runtime artifacts

This procedure removes historical runtime/user-data artifacts from all local branch and tag refs while preserving the rest of the Git commit structure as git-filter-repo normally does.

Confirmed historical paths to remove:

- memory.db
- __init__.cpython-314.pyc
- system.cpython-314.pyc

The old memory.db is a valid SQLite database and contains user-specific MyAI project memories. It must therefore be treated as user data even though no password, API token, financial record or other obvious high-risk secret was observed during the read-only inspection.

## Preconditions

1. Pause all pushes to the repository.
2. Ensure the latest intended MyAI branch state is already on GitHub.
3. Temporarily allow force-pushes if branch protection blocks the rewrite.
4. Tell collaborators not to push old clones after the rewrite.
5. Keep the backup bundle below private and offline. It contains the old history and therefore the data being removed.

## 1. Create a fresh mirror clone

~~~bash
git clone --mirror https://github.com/Harrokk/Myai.git Myai-history-clean.git
cd Myai-history-clean.git
~~~

Do not reuse an old working clone for this operation.

## 2. Create a private rollback bundle

~~~bash
git bundle create ../Myai-before-history-cleanup.bundle --all
~~~

Store this bundle privately. Never commit or upload it back to the public repository.

## 3. Verify the unwanted paths are present before rewriting

~~~bash
git log --all --full-history -- memory.db __init__.cpython-314.pyc system.cpython-314.pyc
~~~

The historical commits should be visible at this point.

## 4. Rewrite all refs with git-filter-repo

Install git-filter-repo if necessary, then run:

~~~bash
git filter-repo --force --invert-paths --path memory.db --path __init__.cpython-314.pyc --path system.cpython-314.pyc
~~~

Do not replace this with a squash commit. A squash would discard useful project history instead of selectively removing the unwanted blobs.

## 5. Verify the paths are gone locally

The following command must produce no commit output:

~~~bash
git log --all --full-history -- memory.db __init__.cpython-314.pyc system.cpython-314.pyc
~~~

Also verify no matching object paths remain:

~~~bash
git rev-list --objects --all | grep -E '(^|/)(memory\.db|__init__\.cpython-314\.pyc|system\.cpython-314\.pyc)$'
~~~

PowerShell equivalent:

~~~powershell
git rev-list --objects --all | Select-String -Pattern '(^|/)(memory\.db|__init__\.cpython-314\.pyc|system\.cpython-314\.pyc)$'
~~~

Both checks must return no matching paths.

## 6. Restore the GitHub remote if filter-repo removed it

Check:

~~~bash
git remote -v
~~~

If origin is missing:

~~~bash
git remote add origin https://github.com/Harrokk/Myai.git
~~~

Otherwise:

~~~bash
git remote set-url origin https://github.com/Harrokk/Myai.git
~~~

## 7. Force-push rewritten branches and tags

Only after local verification succeeds:

~~~bash
git push --force --all origin
git push --force --tags origin
~~~

If GitHub rejects protected branches, stop and adjust branch protection deliberately rather than bypassing unrelated safety controls.

## 8. Post-rewrite verification

From a brand-new clone:

~~~bash
git log --all --full-history -- memory.db __init__.cpython-314.pyc system.cpython-314.pyc
~~~

It must return no matching history.

Also confirm:

- the current VENTUNO integration branch still contains the expected code,
- CI is green on the rewritten branch heads,
- PR #85 still points at the intended VENTUNO integration state,
- no stale local clone is pushed back to GitHub.

## 9. GitHub cached views and pull-request refs

A force-pushed history rewrite removes the files from normal branch/tag history, but GitHub may retain cached commit pages or internal pull-request refs for some time.

If complete public elimination is required, request GitHub's sensitive-data/history purge after the rewrite and provide the old commit/blob identifiers if requested.

Known old identifiers from the audit:

- initial upload commit: 60f87698784e42788d0b0640927c73a6104612d9
- later commit touching/removing the historical artifacts: 31b0392684865c05c2626249caa777face8dffe1
- old memory.db blob: a9c6c6b8146feb07fc61978ab1692ab28878b907

## 10. Prevention already in place

Current repository protections include:

- *.db
- *.db-wal
- *.db-shm
- *.py[cod]
- __pycache__/
- runtime directory ignore rules
- CI guard that fails if database/bytecode artifacts are tracked again

The history rewrite is therefore cleanup of old commits, not a substitute for current repository hygiene.
