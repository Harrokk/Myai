from pathlib import Path

from modules.files import excel


class FakeSheet:
    def __init__(self, title="Sheet"):
        self.title = title
        self.rows = []
        self.freeze_panes = None

    def append(self, row):
        self.rows.append(list(row))

    @property
    def max_row(self):
        return len(self.rows)

    @property
    def max_column(self):
        return max((len(row) for row in self.rows), default=0)

    def iter_rows(self, values_only=False):
        for row in self.rows:
            yield tuple(row)


class FakeWorkbook:
    def __init__(self, rows=None):
        self.active = FakeSheet()
        self.closed = False

        for row in rows or []:
            self.active.append(row)

    def save(self, path):
        Path(path).write_bytes(b"fake-xlsx")

    def close(self):
        self.closed = True


class FakeOpenpyxl:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.created = []
        self.loaded = []

    def Workbook(self):
        workbook = FakeWorkbook()
        self.created.append(workbook)
        return workbook

    def load_workbook(self, path, read_only=False, data_only=False):
        workbook = FakeWorkbook(self.rows)
        self.loaded.append(
            {
                "path": Path(path),
                "read_only": read_only,
                "data_only": data_only,
                "workbook": workbook,
            }
        )
        return workbook


def settings(tmp_path, excel_write=False):
    return {
        "files": {
            "enabled": True,
            "workspace_root": str(tmp_path / "workspace"),
        },
        "excel": {
            "enabled": True,
            "write_enabled": excel_write,
            "max_rows_read": 100,
            "default_sheet": "Data",
        },
    }


def test_parse_create_request_reads_columns_and_rows():
    request = excel.parse_create_request(
        'Skapa Excel-filen "budget.xlsx" med kolumner '
        "Namn, Belopp och rader Kaffe, 35; Lunch, 120"
    )

    assert request["path"] == "budget.xlsx"
    assert request["headers"] == ["Namn", "Belopp"]
    assert request["rows"] == [
        ["Kaffe", 35],
        ["Lunch", 120],
    ]


def test_parse_create_request_preserves_formula():
    request = excel.parse_create_request(
        'Skapa Excel-filen "calc.xlsx" med kolumner '
        "Namn, Summa och rader Test, =1+2"
    )

    assert request["rows"][0][1] == "=1+2"


def test_parse_create_request_rejects_row_width_mismatch():
    try:
        excel.parse_create_request(
            'Skapa Excel-filen "bad.xlsx" med kolumner '
            "A, B och rader 1"
        )
    except ValueError as error:
        assert "samma antal" in str(error)
    else:
        raise AssertionError("Mismatched row width should fail")


def test_parse_append_request_reads_row():
    request = excel.parse_append_request(
        'Lägg till raden Kaffe, 35 i "budget.xlsx".'
    )

    assert request == {
        "path": "budget.xlsx",
        "row": ["Kaffe", 35],
    }


def test_create_excel_is_write_disabled_by_default(tmp_path):
    request = {
        "path": "budget.xlsx",
        "headers": ["Namn", "Belopp"],
        "rows": [["Kaffe", 35]],
    }

    try:
        excel.create_excel_file(
            request,
            settings(tmp_path, excel_write=False),
            openpyxl_module=FakeOpenpyxl(),
        )
    except RuntimeError as error:
        assert "avstängd" in str(error)
    else:
        raise AssertionError("Excel write should be disabled")


def test_create_excel_uses_workspace_and_atomic_save(tmp_path):
    fake = FakeOpenpyxl()
    result = excel.create_excel_file(
        {
            "path": "budget.xlsx",
            "headers": ["Namn", "Belopp"],
            "rows": [["Kaffe", 35]],
        },
        settings(tmp_path, excel_write=True),
        openpyxl_module=fake,
    )

    assert result["path"] == (tmp_path / "workspace" / "budget.xlsx").resolve()
    assert result["columns"] == 2
    assert result["rows_written"] == 1
    assert fake.created[0].active.rows == [
        ["Namn", "Belopp"],
        ["Kaffe", 35],
    ]
    assert fake.created[0].active.freeze_panes == "A2"
    assert result["path"].exists()


def test_read_excel_returns_rows_and_closes_workbook(tmp_path):
    cfg = settings(tmp_path, excel_write=True)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")
    fake = FakeOpenpyxl(
        rows=[
            ["Namn", "Belopp"],
            ["Kaffe", 35],
        ]
    )

    result = excel.read_excel_file(
        "budget.xlsx",
        cfg,
        openpyxl_module=fake,
    )

    assert result["rows"][1] == ["Kaffe", 35]
    assert result["total_rows"] == 2
    assert fake.loaded[0]["workbook"].closed is True


def test_append_excel_requires_matching_column_count(tmp_path):
    cfg = settings(tmp_path, excel_write=True)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")
    fake = FakeOpenpyxl(rows=[["Namn", "Belopp"]])

    try:
        excel.append_excel_row(
            {
                "path": "budget.xlsx",
                "row": ["Kaffe"],
            },
            cfg,
            openpyxl_module=fake,
        )
    except ValueError as error:
        assert "samma antal" in str(error)
    else:
        raise AssertionError("Wrong-width append should fail")


def test_excel_tools_use_user_text_mode():
    assert excel.TOOLS["excel_create"]["input_mode"] == "user_text"
    assert excel.TOOLS["excel_read"]["input_mode"] == "user_text"
    assert excel.TOOLS["excel_append"]["input_mode"] == "user_text"
