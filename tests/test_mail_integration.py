import mail


EXPECTED_TOOLS = {
    "gpu_status",
    "cpu_status",
    "ram_status",
    "temperature_status",
    "disk_status",
}


def test_mail_imports_and_loads_existing_tools():
    assert EXPECTED_TOOLS.issubset(mail.TOOLS.keys())


def test_mail_uses_modular_memory_and_settings():
    assert mail.MODEL == mail.SETTINGS["ollama"]["model"]
    assert mail.MEMORY.database_path.endswith("memory.db")


def test_mail_aliases_point_to_core_components():
    assert mail.TOOLS is mail.CORE.tools
    assert mail.MEMORY is mail.CORE.memory
    assert mail.LLM is mail.CORE.llm


def test_mail_exposes_hardware_monitor_without_starting_on_import():
    assert mail.HARDWARE_MONITOR.interval_seconds == 10
    assert mail.HARDWARE_MONITOR.is_running is False


def test_mail_exposes_device_registry_without_creating_file():
    assert mail.DEVICE_REGISTRY.path.name == "device_registry.json"



class FakeVoiceSession:
    def __init__(self, enabled=True, running=False):
        self.enabled = enabled
        self.running = running
        self.stop_calls = 0

    def status(self):
        return {
            "enabled": self.enabled,
            "running": self.running,
            "microphone": "FakeMic",
            "vad": "FakeVAD",
            "primary_stt": "FakeSTT",
            "backup_stt_count": 2,
            "tts": "FakeTTS",
            "semantic_consensus": False,
        }

    def stop(self):
        self.stop_calls += 1
        self.running = False
        return True


def test_mail_does_not_create_voice_session_on_import():
    assert mail.VOICE_SESSION is None


def test_get_voice_session_is_lazy_and_cached(monkeypatch):
    monkeypatch.setattr(mail, "VOICE_SESSION", None)
    created = []

    def factory():
        session = FakeVoiceSession()
        created.append(session)
        return session

    first = mail.get_voice_session(factory=factory)
    second = mail.get_voice_session(factory=factory)

    assert first is second
    assert len(created) == 1


def test_voice_status_does_not_create_session(monkeypatch):
    monkeypatch.setattr(mail, "VOICE_SESSION", None)
    text = mail.voice_status_text()

    assert "ingen röstsession skapad" in text
    assert mail.VOICE_SESSION is None


def test_voice_status_reports_initialized_session(monkeypatch):
    session = FakeVoiceSession(
        enabled=True,
        running=True,
    )
    monkeypatch.setattr(
        mail,
        "VOICE_SESSION",
        session,
    )

    text = mail.voice_status_text()

    assert "aktivt" in text
    assert "FakeMic" in text
    assert "backup-STT=2" in text


def test_stop_voice_session_is_safe_before_initialization(monkeypatch):
    monkeypatch.setattr(mail, "VOICE_SESSION", None)

    assert mail.stop_voice_session() is False


def test_stop_voice_session_delegates_to_session(monkeypatch):
    session = FakeVoiceSession(
        enabled=True,
        running=True,
    )
    monkeypatch.setattr(
        mail,
        "VOICE_SESSION",
        session,
    )

    assert mail.stop_voice_session() is True
    assert session.stop_calls == 1
