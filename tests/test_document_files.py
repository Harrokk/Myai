import pytest

from modules.documents import files


def use_temp_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "DOCUMENT_ROOT", tmp_path)


def test_safe_text_path_rejects_traversal_and_absolute(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        files._safe_text_path("../outside.txt")

    with pytest.raises(ValueError):
        files._safe_text_path("..\\outside.md")

    with pytest.raises(ValueError):
        files._safe_text_path("C:\\outside.csv")


def test_safe_text_path_rejects_unapproved_suffix(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        files._safe_text_path("script.py")


def test_write_and_read_text_file(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)

    result = files.text_file_write(
        "notes/info.md",
        "# Hej\nText",
    )
    text = files.text_file_read("notes/info.md")

    assert "info.md" in result
    assert text == "# Hej\nText"


def test_write_refuses_overwrite_by_default(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)
    files.text_file_write("notes.txt", "första")

    with pytest.raises(FileExistsError):
        files.text_file_write("notes.txt", "andra")


def test_write_can_explicitly_overwrite(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)
    files.text_file_write("notes.txt", "första")
    files.text_file_write(
        "notes.txt",
        "andra",
        overwrite=True,
    )

    assert files.text_file_read("notes.txt") == "andra"


def test_append_requires_existing_file(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)

    with pytest.raises(FileNotFoundError):
        files.text_file_append("missing.txt", "x")


def test_append_adds_content(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)
    files.text_file_write("notes.txt", "A")
    files.text_file_append("notes.txt", "B")

    assert files.text_file_read("notes.txt") == "AB"


def test_read_truncates_long_content(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)
    files.text_file_write("long.txt", "x" * 100)

    text = files.text_file_read(
        "long.txt",
        max_chars=20,
    )

    assert text.startswith("x" * 20)
    assert "avkortat" in text


def test_document_list_lists_nested_files(tmp_path, monkeypatch):
    use_temp_documents(tmp_path, monkeypatch)
    files.text_file_write("a.txt", "a")
    files.text_file_write("folder/b.md", "b")

    text = files.document_list()

    assert "a.txt" in text
    assert "folder/b.md" in text


def test_tools_declare_parameters_for_mutating_operations():
    for name in (
        "text_file_write",
        "text_file_read",
        "text_file_append",
    ):
        assert "parameters" in files.TOOLS[name]
