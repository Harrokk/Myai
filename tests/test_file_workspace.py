from pathlib import Path

from modules.files import workspace


def settings(tmp_path, write_enabled=False, max_read_chars=20000):
    return {
        "files": {
            "enabled": True,
            "workspace_root": str(tmp_path / "workspace"),
            "write_enabled": write_enabled,
            "max_read_chars": max_read_chars,
            "max_list_entries": 100,
            "allowed_write_extensions": [
                ".txt",
                ".md",
                ".csv",
                ".json",
            ],
        }
    }


def test_resolve_workspace_path_stays_inside_root(tmp_path):
    result = workspace.resolve_workspace_path(
        "notes/test.txt",
        settings(tmp_path),
    )

    assert result == (tmp_path / "workspace" / "notes" / "test.txt").resolve()


def test_resolve_workspace_path_rejects_traversal(tmp_path):
    try:
        workspace.resolve_workspace_path(
            "../secret.txt",
            settings(tmp_path),
        )
    except ValueError as error:
        assert "lämna" in str(error)
    else:
        raise AssertionError("Path traversal should fail")


def test_resolve_workspace_path_rejects_absolute_path(tmp_path):
    try:
        workspace.resolve_workspace_path(
            "/tmp/secret.txt",
            settings(tmp_path),
        )
    except ValueError as error:
        assert "Absoluta" in str(error)
    else:
        raise AssertionError("Absolute path should fail")


def test_extract_file_path_handles_quotes_and_plain_name():
    assert (
        workspace.extract_file_path('Läs filen "notes/test.txt".')
        == "notes/test.txt"
    )
    assert (
        workspace.extract_file_path("Läs filen test.txt")
        == "test.txt"
    )


def test_extract_write_content_from_natural_phrase():
    text = (
        'Skapa filen "note.txt" med innehållet '
        "Hej världen"
    )

    assert workspace.extract_write_content(text) == "Hej världen"


def test_write_is_disabled_by_default(tmp_path):
    try:
        workspace.write_workspace_text(
            "note.txt",
            "Hej",
            settings(tmp_path, write_enabled=False),
        )
    except RuntimeError as error:
        assert "avstängd" in str(error)
    else:
        raise AssertionError("Write should be disabled")


def test_write_and_read_text_inside_workspace(tmp_path):
    cfg = settings(tmp_path, write_enabled=True)

    written = workspace.write_workspace_text(
        "notes/note.txt",
        "Hej världen",
        cfg,
    )
    read = workspace.read_workspace_text(
        "notes/note.txt",
        cfg,
    )

    assert written["chars_written"] == 11
    assert read["content"] == "Hej världen"
    assert read["truncated"] is False


def test_general_writer_rejects_python_files(tmp_path):
    cfg = settings(tmp_path, write_enabled=True)

    try:
        workspace.write_workspace_text(
            "danger.py",
            "print('x')",
            cfg,
        )
    except ValueError as error:
        assert "inte tillåten" in str(error)
    else:
        raise AssertionError("Python writes should be rejected")


def test_read_truncates_large_text(tmp_path):
    cfg = settings(
        tmp_path,
        write_enabled=True,
        max_read_chars=5,
    )
    workspace.write_workspace_text(
        "note.txt",
        "123456789",
        cfg,
    )

    result = workspace.read_workspace_text(
        "note.txt",
        cfg,
    )

    assert result["content"] == "12345"
    assert result["truncated"] is True
    assert result["total_chars"] == 9


def test_list_workspace_files_is_relative(tmp_path):
    cfg = settings(tmp_path, write_enabled=True)
    workspace.write_workspace_text("a.txt", "A", cfg)
    workspace.write_workspace_text("nested/b.md", "B", cfg)

    entries = workspace.list_workspace_files(cfg)

    assert [item["path"] for item in entries] == [
        "a.txt",
        "nested/b.md",
    ]


def test_tool_registry_uses_user_text_input():
    assert workspace.TOOLS["workspace_list"]["pass_user_input"] is True
    assert workspace.TOOLS["workspace_read"]["pass_user_input"] is True
    assert workspace.TOOLS["workspace_write"]["pass_user_input"] is True


def test_workspace_write_tool_audits_without_logging_content(
    tmp_path,
    monkeypatch,
):
    cfg = settings(
        tmp_path,
        write_enabled=True,
    )
    cfg["audit_logging"] = {
        "enabled": True,
        "require_for_writes": True,
        "path": "runtime/audit.jsonl",
        "max_detail_chars": 200,
        "recent_limit": 20,
    }
    cfg["logging"] = {
        "jsonl_max_bytes": 100000,
        "jsonl_backups": 2,
    }
    monkeypatch.setattr(
        workspace,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        workspace,
        "load_settings",
        lambda: cfg,
    )

    result = workspace.workspace_write(
        'Skapa filen "note.txt" med innehållet TOP_SECRET_PAYLOAD.'
    )

    assert "sparades" in result
    audit_path = (
        tmp_path
        / "runtime"
        / "audit.jsonl"
    )
    audit_text = audit_path.read_text(
        encoding="utf-8"
    )

    assert "workspace_write" in audit_text
    assert '"outcome":"attempt"' in audit_text
    assert '"outcome":"success"' in audit_text
    assert "TOP_SECRET_PAYLOAD" not in audit_text


def test_workspace_write_disabled_is_audited_as_denied(
    tmp_path,
    monkeypatch,
):
    cfg = settings(
        tmp_path,
        write_enabled=False,
    )
    cfg["audit_logging"] = {
        "enabled": True,
        "require_for_writes": True,
        "path": "runtime/audit.jsonl",
        "max_detail_chars": 200,
        "recent_limit": 20,
    }
    monkeypatch.setattr(
        workspace,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        workspace,
        "load_settings",
        lambda: cfg,
    )

    result = workspace.workspace_write(
        'Skapa filen "note.txt" med innehållet Hej.'
    )

    assert "avstängd" in result
    audit_text = (
        tmp_path
        / "runtime"
        / "audit.jsonl"
    ).read_text(
        encoding="utf-8"
    )
    assert '"outcome":"attempt"' in audit_text
    assert '"outcome":"denied"' in audit_text
    assert not (
        tmp_path
        / "workspace"
        / "note.txt"
    ).exists()
