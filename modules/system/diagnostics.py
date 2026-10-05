from core.config import (
    PROJECT_ROOT,
    load_settings,
)
from core.diagnostics import (
    build_diagnostic_report,
    format_diagnostic_report,
)


def read_myai_diagnostic_report(
    settings=None,
):
    settings = (
        settings
        or load_settings()
    )
    return build_diagnostic_report(
        settings,
        PROJECT_ROOT,
    )


def myai_diagnostic_report():
    return format_diagnostic_report(
        read_myai_diagnostic_report()
    )


TOOLS = {
    "myai_diagnostic_report": {
        "function": myai_diagnostic_report,
        "description": (
            "Samlar read-only MyAI-diagnostik från konfiguration, "
            "health, runtime-heartbeat, senaste fel, audit och "
            "deployment-lock utan att köra fysisk preflight."
        ),
    },
}
