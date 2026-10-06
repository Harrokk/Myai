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



class OneShotVoiceSession(FakeVoiceSession):
    def __init__(self, result=None, error=None, enabled=True):
        super().__init__(
            enabled=enabled,
            running=False,
        )
        self.result = result or {
            "status": "utterance_complete",
        }
        self.error = error
        self.run_calls = 0

    def run_once(self):
        self.run_calls += 1

        if self.error is not None:
            raise self.error

        self.running = True
        return self.result


def test_run_voice_once_stops_session_after_success():
    session = OneShotVoiceSession()

    result = mail.run_voice_once(
        session=session
    )

    assert result["status"] == "utterance_complete"
    assert session.run_calls == 1
    assert session.stop_calls == 1


def test_run_voice_once_stops_session_after_error():
    session = OneShotVoiceSession(
        error=RuntimeError("testfel")
    )

    try:
        mail.run_voice_once(
            session=session
        )
    except RuntimeError as error:
        assert "testfel" in str(error)
    else:
        raise AssertionError("Voice error should propagate")

    assert session.stop_calls == 1


def test_run_voice_once_does_not_start_disabled_session():
    session = OneShotVoiceSession(
        enabled=False
    )

    result = mail.run_voice_once(
        session=session
    )

    assert result["status"] == "disabled"
    assert session.run_calls == 0
    assert session.stop_calls == 0



class FakeHandsfree:
    def __init__(self, running=False, stop_result=True):
        self.is_running = running
        self.stop_result = stop_result
        self.start_calls = 0
        self.stop_calls = 0
        self.stop_timeout = None

    def start(self):
        self.start_calls += 1

        if self.is_running:
            return False

        self.is_running = True
        return True

    def stop(self, timeout=3.0):
        self.stop_calls += 1
        self.stop_timeout = timeout
        self.is_running = False
        return self.stop_result


def test_mail_does_not_create_handsfree_runner_on_import():
    assert mail.VOICE_HANDSFREE is None


def test_get_voice_handsfree_is_lazy_and_cached(monkeypatch):
    monkeypatch.setattr(
        mail,
        "VOICE_HANDSFREE",
        None,
    )
    created = []

    def factory():
        runner = FakeHandsfree()
        created.append(runner)
        return runner

    first = mail.get_voice_handsfree(
        factory=factory
    )
    second = mail.get_voice_handsfree(
        factory=factory
    )

    assert first is second
    assert len(created) == 1


def test_stop_voice_handsfree_is_safe_before_initialization(monkeypatch):
    monkeypatch.setattr(
        mail,
        "VOICE_HANDSFREE",
        None,
    )

    assert mail.stop_voice_handsfree() is False


def test_stop_voice_handsfree_uses_configured_timeout(monkeypatch):
    runner = FakeHandsfree(
        running=True
    )
    monkeypatch.setattr(
        mail,
        "VOICE_HANDSFREE",
        runner,
    )

    assert mail.stop_voice_handsfree() is True
    assert runner.stop_calls == 1
    assert runner.stop_timeout == mail.SETTINGS[
        "voice"
    ].get(
        "handsfree_stop_timeout_seconds",
        3.0,
    )


def test_voice_status_reports_active_handsfree(monkeypatch):
    session = FakeVoiceSession(
        enabled=True,
        running=True,
    )
    runner = FakeHandsfree(
        running=True
    )
    monkeypatch.setattr(
        mail,
        "VOICE_SESSION",
        session,
    )
    monkeypatch.setattr(
        mail,
        "VOICE_HANDSFREE",
        runner,
    )

    text = mail.voice_status_text()

    assert "handsfree=aktivt" in text


def test_stop_voice_session_stops_handsfree_and_session(monkeypatch):
    session = FakeVoiceSession(
        enabled=True,
        running=True,
    )
    runner = FakeHandsfree(
        running=True
    )
    monkeypatch.setattr(
        mail,
        "VOICE_SESSION",
        session,
    )
    monkeypatch.setattr(
        mail,
        "VOICE_HANDSFREE",
        runner,
    )

    assert mail.stop_voice_session() is True
    assert runner.stop_calls == 1
    assert session.stop_calls == 1



def test_stop_voice_handsfree_reports_false_when_already_stopped(monkeypatch):
    runner = FakeHandsfree(
        running=False,
        stop_result=True,
    )
    monkeypatch.setattr(
        mail,
        "VOICE_HANDSFREE",
        runner,
    )

    assert mail.stop_voice_handsfree() is False
    assert runner.stop_calls == 1



class FakeTerminalHandoff:
    def __init__(self, running=False):
        self.is_running = running
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

        if self.is_running:
            return False

        self.is_running = True
        return True

    def stop(self, timeout=3.0):
        self.stop_calls += 1
        self.is_running = False
        return True

    def status(self):
        return {
            "enabled": True,
            "running": self.is_running,
            "auto_execute": False,
            "scan_interval_seconds": 5.0,
            "tracked_terminals": {},
        }


def test_mail_does_not_create_terminal_handoff_on_import():
    assert mail.TERMINAL_HANDOFF is None


def test_get_terminal_handoff_is_lazy_and_cached(monkeypatch):
    monkeypatch.setattr(mail, "TERMINAL_HANDOFF", None)
    created = []

    def factory():
        monitor = FakeTerminalHandoff()
        created.append(monitor)
        return monitor

    first = mail.get_terminal_handoff(factory=factory)
    second = mail.get_terminal_handoff(factory=factory)

    assert first is second
    assert len(created) == 1


def test_terminal_status_does_not_create_monitor(monkeypatch):
    monkeypatch.setattr(mail, "TERMINAL_HANDOFF", None)

    text = mail.terminal_handoff_status_text()

    assert "ingen monitor skapad" in text
    assert mail.TERMINAL_HANDOFF is None


def test_terminal_status_reports_running_monitor(monkeypatch):
    monitor = FakeTerminalHandoff(running=True)
    monkeypatch.setattr(mail, "TERMINAL_HANDOFF", monitor)

    text = mail.terminal_handoff_status_text()

    assert "aktiv" in text
    assert "auto_execute=False" in text


def test_stop_terminal_handoff_is_safe_before_initialization(monkeypatch):
    monkeypatch.setattr(mail, "TERMINAL_HANDOFF", None)

    assert mail.stop_terminal_handoff() is False


def test_stop_terminal_handoff_delegates_to_monitor(monkeypatch):
    monitor = FakeTerminalHandoff(running=True)
    monkeypatch.setattr(mail, "TERMINAL_HANDOFF", monitor)

    assert mail.stop_terminal_handoff() is True
    assert monitor.stop_calls == 1


def test_required_preflight_skips_when_ventuno_is_disabled(
    monkeypatch,
):
    monkeypatch.setattr(
        mail,
        "SETTINGS",
        {
            "ventuno": {
                "enabled": False,
            },
            "runtime": {
                "require_preflight": True,
            },
        },
    )

    def fail_runner(
        settings,
    ):
        raise AssertionError(
            "Preflight ska inte köras för icke-VENTUNO."
        )

    result = mail.required_preflight(
        runner=fail_runner
    )

    assert result == {
        "required": False,
        "passed": True,
    }


def test_required_preflight_blocks_failed_ventuno_check(
    monkeypatch,
):
    monkeypatch.setattr(
        mail,
        "SETTINGS",
        {
            "ventuno": {
                "enabled": True,
            },
            "runtime": {
                "require_preflight": True,
            },
        },
    )

    result = mail.required_preflight(
        runner=lambda settings: {
            "passed": False,
            "checks": [],
        }
    )

    assert result[
        "required"
    ] is True
    assert result[
        "passed"
    ] is False


def test_manual_memory_write_requires_audit_attempt(
    monkeypatch,
):
    class Memory:
        def __init__(
            self,
        ):
            self.calls = 0

        def save(
            self,
            category,
            content,
        ):
            self.calls += 1
            return 7

    class Audit:
        def write_attempt(
            self,
            **kwargs,
        ):
            raise RuntimeError(
                "audit unavailable"
            )

        def write_result(
            self,
            **kwargs,
        ):
            raise AssertionError(
                "result får inte skrivas när attempt misslyckas"
            )

    memory = Memory()
    monkeypatch.setattr(
        mail,
        "MEMORY",
        memory,
    )
    monkeypatch.setattr(
        mail.CORE,
        "audit_logger",
        Audit(),
    )

    try:
        mail.save_manual_memory(
            "testminne"
        )
    except RuntimeError as error:
        assert "audit unavailable" in str(
            error
        )
    else:
        raise AssertionError(
            "Auditfel måste blockera minnesskrivning."
        )

    assert memory.calls == 0


def test_manual_memory_result_audit_is_best_effort(
    monkeypatch,
):
    seen = {
        "attempt": None,
    }

    class Memory:
        def save(
            self,
            category,
            content,
        ):
            assert category == "manual"
            assert content == "privat testinnehåll"
            return 9

    class Audit:
        def write_attempt(
            self,
            **kwargs,
        ):
            seen[
                "attempt"
            ] = kwargs

        def write_result(
            self,
            **kwargs,
        ):
            raise RuntimeError(
                "syntetiskt resultatloggfel"
            )

    monkeypatch.setattr(
        mail,
        "MEMORY",
        Memory(),
    )
    monkeypatch.setattr(
        mail.CORE,
        "audit_logger",
        Audit(),
    )

    memory_id = mail.save_manual_memory(
        "privat testinnehåll"
    )

    assert memory_id == 9
    assert seen[
        "attempt"
    ][
        "action"
    ] == "memory_manual_store"
    assert "privat testinnehåll" not in str(
        seen[
            "attempt"
        ]
    )
