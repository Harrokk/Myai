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
