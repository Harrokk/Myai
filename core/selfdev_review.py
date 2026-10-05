import difflib
import json


def _read_lines(path):
    if not path.exists():
        return []

    return path.read_text(
        encoding="utf-8",
    ).splitlines(
        keepends=True,
    )


def build_selfdev_review(
    workspace,
    *,
    max_diff_chars=100_000,
):
    changes = (
        workspace
        .changed_files()
    )
    paths = sorted(
        changes[
            "changed"
        ]
        + changes[
            "added"
        ]
        + changes[
            "deleted"
        ]
    )
    sections = []

    for relative in paths:
        source = (
            workspace
            .project_root
            / relative
        )
        candidate = (
            workspace
            .workspace_root
            / relative
        )
        before = _read_lines(
            source
        )
        after = _read_lines(
            candidate
        )
        diff = "".join(
            difflib.unified_diff(
                before,
                after,
                fromfile=(
                    "active/"
                    + relative
                ),
                tofile=(
                    "staging/"
                    + relative
                ),
            )
        )

        if diff:
            sections.append(
                diff
            )

    combined = "\n".join(
        sections
    )
    truncated = False

    if len(
        combined
    ) > max_diff_chars:
        combined = combined[
            :max_diff_chars
        ]
        combined += (
            "\n... [diff trunkerad]"
        )
        truncated = True

    verification = None

    if (
        workspace
        .verification_path
        .exists()
    ):
        try:
            verification = json.loads(
                workspace
                .verification_path
                .read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            verification = {
                "passed": False,
                "error": (
                    "verification.json kunde inte läsas"
                ),
            }

    return {
        "session_id": (
            workspace.session_id
        ),
        "changed": (
            changes[
                "changed"
            ]
        ),
        "added": (
            changes[
                "added"
            ]
        ),
        "deleted": (
            changes[
                "deleted"
            ]
        ),
        "source_drift": (
            workspace
            .source_drift()
        ),
        "verification": (
            verification
        ),
        "diff": combined,
        "diff_truncated": (
            truncated
        ),
    }
