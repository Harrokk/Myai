from core.config import load_settings
from core.geniex_supervisor import GenieXSupervisor
from modules.ventuno.telemetry import read_thermal_status


def geniex_status():
    settings = load_settings()
    supervisor = GenieXSupervisor(
        settings
    )
    result = supervisor.check()

    if result["status"] == "disabled":
        return (
            "GenieX supervisor är avstängd. "
            "Ingen health-check utfördes."
        )

    if result["healthy"]:
        return (
            "GenieX: ready\n"
            f"Endpoint: {result['models_url']}\n"
            f"Tillgängliga modeller: {result['model_count']}\n"
            f"Misslyckade kontroller i rad: "
            f"{result['consecutive_failures']}\n"
            f"Automatisk restart: "
            f"{supervisor.restart_enabled}"
        )

    return (
        "GenieX: unhealthy\n"
        f"Endpoint: {result['models_url']}\n"
        f"Misslyckade kontroller i rad: "
        f"{result['consecutive_failures']}\n"
        f"Fel: {result['error']}\n"
        f"Automatisk restart: "
        f"{supervisor.restart_enabled}"
    )


def ventuno_accelerator_status():
    settings = load_settings()
    assistant = settings.get(
        "assistant",
        {},
    )
    geniex = settings.get(
        "geniex",
        {},
    )
    supervisor = GenieXSupervisor(
        settings
    )
    result = supervisor.check()

    if result[
        "status"
    ] == "disabled":
        readiness = "supervisor avstängd"
    elif result.get(
        "healthy"
    ):
        readiness = "GenieX ready"
    else:
        readiness = (
            "GenieX unhealthy: "
            + str(
                result.get(
                    "error"
                )
                or "okänt fel"
            )
        )

    thermal = read_thermal_status()
    if thermal["temperatures_c"]:
        thermal_report = (
            f"- NSP/DSP-temperatur: "
            f"{thermal['min_c']:.1f}–{thermal['max_c']:.1f} °C "
            f"(medel {thermal['avg_c']:.1f} °C, "
            f"{len(thermal['temperatures_c'])} sensorer)\n"
        )
    else:
        thermal_report = "- NSP/DSP-temperatur: ej tillgänglig\n"

    if thermal["cooling_state"] is not None:
        thermal_report += (
            f"- DSP termiskt tillstånd: "
            f"{thermal['cooling_state']}/"
            f"{thermal['cooling_max_state']}\n"
        )
    else:
        thermal_report += "- DSP termiskt tillstånd: ej tillgängligt\n"

    return (
        "VENTUNO AI-acceleratorstatus (read-only):\n"
        f"- Konfigurerad accelerator: "
        f"{assistant.get('compute_accelerator') or 'Qualcomm QCS8275 / Hexagon NPU'}\n"
        f"- GenieX-modell: "
        f"{geniex.get('model') or 'saknas'}\n"
        f"- Backend readiness: {readiness}\n"
        f"{thermal_report}"
        "- Direkt NPU-belastning och NPU-frekvens rapporteras inte ännu. "
        "NSP/DSP-temperatur är inte verifierad som NPU-kärntemperatur."
    )


TOOLS = {
    "geniex_status": {
        "function": geniex_status,
        "description": (
            "Gör en read-only readiness-kontroll av den lokala "
            "GenieX-servern via /v1/models. Kan inte starta om tjänsten."
        ),
    },
    "ventuno_accelerator_status": {
        "function": ventuno_accelerator_status,
        "description": (
            "Visar read-only VENTUNO/QCS8275 accelerator- och GenieX-status "
            "utan att påstå direkt NPU-utnyttjande när sådan telemetri "
            "inte är fysiskt verifierad."
        ),
    },
}
