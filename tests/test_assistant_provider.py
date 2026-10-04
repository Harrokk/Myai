from copy import deepcopy

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.geniex_client import GenieXClient


class FakeMemory:
    def search(self, user_message):
        return []

    @staticmethod
    def format(memories):
        return "Ingen relevant information hittades."


def test_core_selects_geniex_without_changing_callers(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["llm"]["provider"] = "geniex"

    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=FakeMemory(),
    )

    assert isinstance(core.llm, GenieXClient)
    assert core.llm_provider == "geniex"
    assert core.model == settings["geniex"]["model"]
    assert core.llm_url.endswith("/v1/chat/completions")
    assert "Qualcomm GenieX" in core.system_profile
    assert "Arduino VENTUNO Q" in core.system_profile
