from modules.ventuno import geniex


class FakeSupervisor:
    restart_enabled = False

    def __init__(self, settings):
        self.settings = settings

    def check(self):
        return {
            "status": "ready",
            "healthy": True,
            "models_url": (
                "http://127.0.0.1:18181/v1/models"
            ),
            "model_count": 2,
            "consecutive_failures": 0,
        }


def test_geniex_status_is_read_only(monkeypatch):
    monkeypatch.setattr(
        geniex,
        "load_settings",
        lambda: {},
    )
    monkeypatch.setattr(
        geniex,
        "GenieXSupervisor",
        FakeSupervisor,
    )

    result = geniex.geniex_status()

    assert "GenieX: ready" in result
    assert "Tillgängliga modeller: 2" in result
    assert "Automatisk restart: False" in result


def test_geniex_tool_exposes_no_restart_action():
    assert set(
        geniex.TOOLS
    ) == {
        "geniex_status",
    }
