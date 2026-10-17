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

    assert result == "Kunde inte skriva filen: feltext dold."
    assert "avstängd" not in result
    assert not (tmp_path / "workspace" / "note.txt").exists()
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


def test_preexisting_temporary_symlink_does_not_escape_workspace(tmp_path):
    cfg = settings(tmp_path, write_enabled=True)
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "important.txt"
    outside.write_text("UNCHANGED", encoding="utf-8")
    (root / "note.txt.tmp").symlink_to(outside)

    result = workspace.write_workspace_text("note.txt", "Safe", cfg)
    assert result["chars_written"] == 4
    assert outside.read_text(encoding="utf-8") == "UNCHANGED"
    assert (root / "note.txt").read_text(encoding="utf-8") == "Safe"
    assert (root / "note.txt.tmp").is_symlink()


def test_workspace_listing_ignores_symbolic_link_to_external_file(tmp_path):
    cfg = settings(tmp_path, write_enabled=True)
    root = tmp_path / "workspace"
    root.mkdir()
    external = tmp_path / "private.txt"
    external.write_text("PRIVATE_METADATA", encoding="utf-8")
    (root / "outside.txt").symlink_to(external)
    (root / "safe.txt").write_text("ok", encoding="utf-8")

    entries = workspace.list_workspace_files(cfg)
    assert [entry["path"] for entry in entries] == ["safe.txt"]


def test_failed_atomic_write_cleans_only_new_temporary_file(tmp_path, monkeypatch):
    cfg = settings(tmp_path, write_enabled=True)
    root = tmp_path / "workspace"
    root.mkdir()
    destination = root / "note.txt"
    destination.write_text("old", encoding="utf-8")
    old_replace = workspace.os.replace

    def denied_replace(source, target):
        assert target == destination
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(workspace.os, "replace", denied_replace)
    try:
        workspace.write_workspace_text("note.txt", "new", cfg)
    except OSError as error:
        assert "simulated" in str(error)
    else:
        raise AssertionError("Atomic replace failure must propagate")
    finally:
        monkeypatch.setattr(workspace.os, "replace", old_replace)

    assert destination.read_text(encoding="utf-8") == "old"
    assert sorted(path.name for path in root.iterdir()) == ["note.txt"]


def test_workspace_read_large_unicode_file_uses_bounded_blocks(tmp_path, monkeypatch):
    """Memory usage may grow with max_read_chars, not the input file size."""
    cfg = settings(tmp_path, max_read_chars=5)
    root = tmp_path / "workspace"
    root.mkdir()
    source = root / "large.txt"
    source.write_text("åäö" * 100_000, encoding="utf-8")

    real_open = Path.open
    block_sizes = []

    class BoundedReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, tb):
            return self.stream.__exit__(exc_type, exc_value, tb)

        def read(self, size=-1):
            assert 0 < size <= 16_384, "Workspace tried an unbounded read"
            block_sizes.append(size)
            return self.stream.read(size)

    def guarded_open(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        if path == source:
            return BoundedReader(stream)
        return stream

    monkeypatch.setattr(Path, "open", guarded_open)
    result = workspace.read_workspace_text("large.txt", cfg)
    assert result == {
        "path": "large.txt",
        "content": "åäöåä",
        "truncated": True,
        "total_chars": 300_000,
    }
    assert len(block_sizes) > 2
    assert max(block_sizes) <= 16_384


def test_workspace_read_invalid_utf8_late_in_file_fails_closed(tmp_path):
    """A truncated excerpt must not hide invalid UTF-8 later in the file."""
    cfg = settings(tmp_path, max_read_chars=5)
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "broken.txt").write_bytes(b"A" * 40_000 + b"\\xff")

    try:
        workspace.read_workspace_text("broken.txt", cfg)
    except ValueError as error:
        assert "UTF-8" in str(error)
    else:
        raise AssertionError("Invalid UTF-8 must be rejected")


def test_workspace_read_exact_limit_reports_not_truncated(tmp_path):
    cfg = settings(tmp_path, max_read_chars=3)
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "exact.txt").write_text("åäö", encoding="utf-8")
    result = workspace.read_workspace_text("exact.txt", cfg)
    assert result["content"] == "åäö"
    assert result["total_chars"] == 3
    assert result["truncated"] is False


def test_workspace_listing_stops_before_scanning_later_directories(
    tmp_path, monkeypatch
):
    cfg = settings(tmp_path, write_enabled=True)
    cfg["files"]["max_list_entries"] = 1
    workspace.write_workspace_text("a/first.txt", "one", cfg)
    workspace.write_workspace_text("z/last.txt", "two", cfg)

    real_scandir = workspace.os.scandir
    visited = []

    def traced_scandir(path):
        visited.append(Path(path).name)
        if Path(path).name == "z":
            raise AssertionError("Workspace scanned directories after the cap")
        return real_scandir(path)

    monkeypatch.setattr(workspace.os, "scandir", traced_scandir)
    listed = workspace.list_workspace_files(cfg)
    assert [item["path"] for item in listed] == ["a/first.txt"]
    assert "a" in visited
    assert "z" not in visited


def test_workspace_listing_preserves_full_relative_path_sort(tmp_path):
    cfg = settings(tmp_path, write_enabled=True)
    for name in ("notes/one.txt", "notes0.txt", "notes.txt", "a.txt"):
        workspace.write_workspace_text(name, "x", cfg)
    result = workspace.list_workspace_files(cfg)
    assert [x["path"] for x in result] == [
        "a.txt", "notes.txt", "notes/one.txt", "notes0.txt"
    ]
