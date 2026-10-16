"""Synthetic privacy boundaries for public tool functions.

Do not start real networking, USB, camera, GPS, spreadsheets or any model.
"""
import pytest

from modules.internet import fetch
from modules.files import workspace, excel
from modules.camera import capture
from modules.location import gps

PRIVATE = "token=PLEASE_NEVER_ECHO_THIS_TO_THE_USER"


def _raise(*args, **kwargs):
    raise RuntimeError("private error payload " + PRIVATE)


@pytest.mark.parametrize("fn,owner,patched,argument", [
    (fetch.web_fetch_text, fetch, "fetch_public_page", "https://example.org"),
    (workspace.workspace_list, workspace, "list_workspace_files", ""),
    (workspace.workspace_read, workspace, "extract_file_path", "secret.txt"),
    (workspace.workspace_write, workspace, "extract_file_path", "secret.txt"),
    (excel.excel_list_sheets, excel, "extract_file_path", "book.xlsx"),
    (excel.excel_create_sheet, excel, "load_settings", "make sheet"),
    (excel.excel_create, excel, "load_settings", "make excel"),
    (excel.excel_read, excel, "extract_file_path", "book.xlsx"),
    (excel.excel_set_cell, excel, "load_settings", "set A1"),
    (excel.excel_append, excel, "load_settings", "append"),
    (capture.camera_capture, capture, "capture_from_settings", None),
    (gps.location_status, gps, "read_gps_location", None),
])
def test_tool_result_never_echoes_native_exception(monkeypatch, fn, owner, patched, argument):
    monkeypatch.setattr(owner, patched, _raise)
    result = fn() if argument is None else fn(argument)
    assert isinstance(result, str)
    assert PRIVATE not in result
    assert "private error payload" not in result
    assert "feltext dold" in result
