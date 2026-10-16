"""Legacy on-demand HTP/audio workflow retirement regression; zero hardware."""
from scripts.ventuno_physical_dispatch_quarantine import inspect, ARCHIVED, ROOT


def test_five_legacy_manual_board_workflows_cannot_run():
    report = inspect()
    assert report["status"] == "five-hardware-dispatches-archived-source-only"
    assert report["archived_expected"] == report["archived_verified"] == 5
    assert report["quarantine_passed"] is True
    assert report["physical_htp_or_audio_test_authorized"] is False
    assert report["all_other_workflows_released"] is False


def test_removed_or_reactivated_legacy_entry_is_rejected(tmp_path):
    folder = tmp_path / ".github/workflows"
    folder.mkdir(parents=True)
    for name in ARCHIVED:
        (folder / name).write_bytes((ROOT / ".github/workflows" / name).read_bytes())
    assert inspect(tmp_path)["quarantine_passed"]
    target = folder / ARCHIVED[0]
    target.write_text(target.read_text().replace("if: false", "if: true"))
    assert inspect(tmp_path)["status"].startswith("blocked")
    target.unlink()
    assert inspect(tmp_path)["quarantine_passed"] is False
