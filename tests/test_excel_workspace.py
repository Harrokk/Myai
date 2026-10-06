from pathlib import Path

from modules.files import excel


class FakeCell:
    def __init__(self, value=None):
        self.value = value


class FakeSheet:
    def __init__(self, title="Sheet"):
        self.title = title
        self.rows = []
        self.freeze_panes = None
        self.cells = {}

    def append(self, row):
        self.rows.append(list(row))

    def cell(self, row, column):
        key = (row, column)

        if key not in self.cells:
            value = None

            if row <= len(self.rows) and column <= len(self.rows[row - 1]):
                value = self.rows[row - 1][column - 1]

            self.cells[key] = FakeCell(value)

        return self.cells[key]

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
    def __init__(self, rows=None, sheets=None):
        self.closed = False

        if sheets:
            self._sheets = {}

            for title, sheet_rows in sheets.items():
                sheet = FakeSheet(title=title)

                for row in sheet_rows:
                    sheet.append(row)

                self._sheets[title] = sheet

            self.active = next(iter(self._sheets.values()))
        else:
            self.active = FakeSheet()
            self._sheets = {self.active.title: self.active}

            for row in rows or []:
                self.active.append(row)

    @property
    def sheetnames(self):
        return list(self._sheets.keys())

    def __getitem__(self, name):
        return self._sheets[name]

    def create_sheet(self, title):
        sheet = FakeSheet(title=title)
        self._sheets[title] = sheet
        return sheet

    def save(self, path):
        Path(path).write_bytes(b"fake-xlsx")

    def close(self):
        self.closed = True


class FakeOpenpyxl:
    def __init__(self, rows=None, sheets=None):
        self.rows = rows or []
        self.sheets = sheets
        self.created = []
        self.loaded = []

    def Workbook(self):
        workbook = FakeWorkbook()
        self.created.append(workbook)
        return workbook

    def load_workbook(self, path, read_only=False, data_only=False):
        workbook = FakeWorkbook(self.rows, sheets=self.sheets)
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
        "sheet": None,
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
    assert excel.TOOLS["excel_create"]["pass_user_input"] is True
    assert excel.TOOLS["excel_read"]["pass_user_input"] is True
    assert excel.TOOLS["excel_append"]["pass_user_input"] is True



def test_parse_cell_reference_converts_a1_to_coordinates():
    assert excel.parse_cell_reference("B2") == {
        "reference": "B2",
        "row": 2,
        "column": 2,
    }
    assert excel.parse_cell_reference("AA10") == {
        "reference": "AA10",
        "row": 10,
        "column": 27,
    }


def test_parse_cell_reference_rejects_invalid_reference():
    try:
        excel.parse_cell_reference("2B")
    except ValueError as error:
        assert "A1-format" in str(error)
    else:
        raise AssertionError("Invalid cell reference should fail")


def test_parse_set_cell_request_reads_value_and_formula():
    request = excel.parse_set_cell_request(
        'Sätt B2 till 42 i "budget.xlsx".'
    )

    assert request["path"] == "budget.xlsx"
    assert request["cell"] == "B2"
    assert request["row"] == 2
    assert request["column"] == 2
    assert request["value"] == 42

    formula = excel.parse_set_cell_request(
        'Sätt C2 till =SUM(B2:B10) i "budget.xlsx".'
    )

    assert formula["value"] == "=SUM(B2:B10)"


def test_set_excel_cell_updates_value_and_closes_workbook(tmp_path):
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

    result = excel.set_excel_cell(
        {
            "path": "budget.xlsx",
            "cell": "B2",
            "row": 2,
            "column": 2,
            "value": 40,
        },
        cfg,
        openpyxl_module=fake,
    )

    workbook = fake.loaded[0]["workbook"]
    assert result["previous"] == 35
    assert result["value"] == 40
    assert workbook.active.cell(2, 2).value == 40
    assert workbook.closed is True
    assert path.exists()


def test_set_excel_cell_respects_write_disabled(tmp_path):
    cfg = settings(tmp_path, excel_write=False)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")

    try:
        excel.set_excel_cell(
            {
                "path": "budget.xlsx",
                "cell": "B2",
                "row": 2,
                "column": 2,
                "value": 40,
            },
            cfg,
            openpyxl_module=FakeOpenpyxl(),
        )
    except RuntimeError as error:
        assert "avstängd" in str(error)
    else:
        raise AssertionError("Excel edit should be disabled")


def test_excel_set_cell_tool_uses_user_text_mode():
    assert excel.TOOLS["excel_set_cell"]["pass_user_input"] is True



def test_extract_sheet_name_reads_quoted_name():
    assert (
        excel.extract_sheet_name(
            'Läs Excel-filen "budget.xlsx" på blad "Januari".'
        )
        == "Januari"
    )
    assert excel.extract_sheet_name('Läs "budget.xlsx".') is None


def test_create_request_includes_selected_sheet():
    request = excel.parse_create_request(
        'Skapa Excel-filen "budget.xlsx" på blad "Januari" '
        "med kolumner Namn, Belopp och rader Kaffe, 35"
    )

    assert request["sheet"] == "Januari"


def test_read_excel_selects_named_sheet(tmp_path):
    cfg = settings(tmp_path, excel_write=True)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")
    fake = FakeOpenpyxl(
        sheets={
            "Januari": [["Namn", "Belopp"], ["Kaffe", 35]],
            "Februari": [["Namn", "Belopp"], ["Lunch", 120]],
        }
    )

    result = excel.read_excel_file(
        "budget.xlsx",
        cfg,
        openpyxl_module=fake,
        sheet_name="Februari",
    )

    assert result["sheet"] == "Februari"
    assert result["rows"][1] == ["Lunch", 120]


def test_read_excel_rejects_missing_named_sheet(tmp_path):
    cfg = settings(tmp_path, excel_write=True)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")
    fake = FakeOpenpyxl(
        sheets={
            "Januari": [["Namn", "Belopp"]],
        }
    )

    try:
        excel.read_excel_file(
            "budget.xlsx",
            cfg,
            openpyxl_module=fake,
            sheet_name="Mars",
        )
    except ValueError as error:
        assert "finns inte" in str(error)
    else:
        raise AssertionError("Missing sheet should fail")


def test_append_request_keeps_named_sheet():
    request = excel.parse_append_request(
        'Lägg till raden Kaffe, 35 i "budget.xlsx" på blad "Januari".'
    )

    assert request["sheet"] == "Januari"


def test_set_cell_request_keeps_named_sheet():
    request = excel.parse_set_cell_request(
        'Sätt B2 till 42 i "budget.xlsx" på blad "Januari".'
    )

    assert request["sheet"] == "Januari"



def test_parse_create_sheet_request():
    request = excel.parse_create_sheet_request(
        'Skapa blad "Februari" i "budget.xlsx".'
    )

    assert request == {
        "path": "budget.xlsx",
        "sheet": "Februari",
    }


def test_list_excel_sheets_returns_names_and_active(tmp_path):
    cfg = settings(tmp_path, excel_write=True)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")
    fake = FakeOpenpyxl(
        sheets={
            "Januari": [["Namn", "Belopp"]],
            "Februari": [["Namn", "Belopp"]],
        }
    )

    result = excel.list_excel_sheets(
        "budget.xlsx",
        cfg,
        openpyxl_module=fake,
    )

    assert result["sheets"] == ["Januari", "Februari"]
    assert result["active"] == "Januari"
    assert fake.loaded[0]["workbook"].closed is True


def test_create_excel_sheet_adds_named_sheet(tmp_path):
    cfg = settings(tmp_path, excel_write=True)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")
    fake = FakeOpenpyxl(
        sheets={
            "Januari": [["Namn", "Belopp"]],
        }
    )

    result = excel.create_excel_sheet(
        {
            "path": "budget.xlsx",
            "sheet": "Februari",
        },
        cfg,
        openpyxl_module=fake,
    )

    assert result["sheet"] == "Februari"
    assert "Februari" in result["sheets"]
    assert path.exists()


def test_create_excel_sheet_rejects_duplicate(tmp_path):
    cfg = settings(tmp_path, excel_write=True)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")
    fake = FakeOpenpyxl(
        sheets={
            "Januari": [["Namn"]],
        }
    )

    try:
        excel.create_excel_sheet(
            {
                "path": "budget.xlsx",
                "sheet": "Januari",
            },
            cfg,
            openpyxl_module=fake,
        )
    except ValueError as error:
        assert "finns redan" in str(error)
    else:
        raise AssertionError("Duplicate sheet should fail")


def test_create_excel_sheet_rejects_invalid_name(tmp_path):
    cfg = settings(tmp_path, excel_write=True)
    path = tmp_path / "workspace" / "budget.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"fake")

    try:
        excel.create_excel_sheet(
            {
                "path": "budget.xlsx",
                "sheet": "Bad/Name",
            },
            cfg,
            openpyxl_module=FakeOpenpyxl(),
        )
    except ValueError as error:
        assert "otillåtet" in str(error)
    else:
        raise AssertionError("Invalid sheet name should fail")


def test_sheet_management_tools_use_user_text_mode():
    assert excel.TOOLS["excel_list_sheets"]["pass_user_input"] is True
    assert excel.TOOLS["excel_create_sheet"]["pass_user_input"] is True


def test_excel_create_tool_audits_without_cell_or_row_values(
    tmp_path,
    monkeypatch,
):
    cfg = settings(
        tmp_path,
        excel_write=True,
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
        excel,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        excel,
        "load_settings",
        lambda: cfg,
    )

    def fake_create(
        request,
        settings=None,
    ):
        return {
            "path": (
                tmp_path
                / "workspace"
                / request["path"]
            ),
            "sheet": "Data",
            "rows_written": len(
                request.get(
                    "rows",
                    [],
                )
            ),
            "columns": len(
                request[
                    "headers"
                ]
            ),
        }

    monkeypatch.setattr(
        excel,
        "create_excel_file",
        fake_create,
    )

    result = excel.excel_create(
        'Skapa Excel-filen "budget.xlsx" med kolumner '
        'Namn, Belopp och rader TOP_SECRET_VALUE, 35'
    )

    assert "skapades" in result
    audit_text = (
        tmp_path
        / "runtime"
        / "audit.jsonl"
    ).read_text(
        encoding="utf-8"
    )

    assert "excel_create" in audit_text
    assert '"outcome":"attempt"' in audit_text
    assert '"outcome":"success"' in audit_text
    assert "TOP_SECRET_VALUE" not in audit_text
    assert '"rows":1' in audit_text
    assert '"columns":2' in audit_text


def test_excel_write_disabled_is_audited_as_denied(
    tmp_path,
    monkeypatch,
):
    cfg = settings(
        tmp_path,
        excel_write=False,
    )
    cfg["audit_logging"] = {
        "enabled": True,
        "require_for_writes": True,
        "path": "runtime/audit.jsonl",
        "max_detail_chars": 200,
        "recent_limit": 20,
    }
    monkeypatch.setattr(
        excel,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        excel,
        "load_settings",
        lambda: cfg,
    )

    result = excel.excel_create(
        'Skapa Excel-filen "budget.xlsx" med kolumner '
        'A, B och rader test, 1'
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
