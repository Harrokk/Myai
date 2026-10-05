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


TOOLS = {
    "geniex_status": {
        "function": geniex_status,
        "description": (
            "Gör en read-only readiness-kontroll av den lokala "
            "GenieX-servern via /v1/models. Kan inte starta om tjänsten."
        ),
    },
}
