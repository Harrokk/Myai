from core.config import load_settings
from core.geniex_supervisor import GenieXSupervisor


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

    return (
        "VENTUNO AI-acceleratorstatus (read-only):\n"
        f"- Konfigurerad accelerator: "
        f"{assistant.get('compute_accelerator') or 'Qualcomm QCS8275 / Hexagon NPU'}\n"
        f"- GenieX-modell: "
        f"{geniex.get('model') or 'saknas'}\n"
        f"- Backend readiness: {readiness}\n"
        "- Direkt NPU-belastning, frekvens och NPU-temperatur "
        "rapporteras inte ännu. MyAI väntar på en verifierad "
        "QCS8275/VENTUNO-telemetriväg på fysisk hårdvara i stället "
        "för att tolka GenieX-readiness som NPU-utnyttjande."
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
