import platform
import subprocess


def _run_command(command, encoding=None):
    options = {
        "capture_output": True,
        "timeout": 15,
    }

    if encoding:
        options["encoding"] = encoding
        options["errors"] = "replace"
    else:
        options["text"] = True

    return subprocess.run(
        command,
        **options,
    )


def _format_lines(output, title="Bluetooth-enheter", max_lines=50):
    lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip()
    ]

    if not lines:
        return "Inga Bluetooth-enheter hittades."

    visible = lines[:max_lines]
    result = f"{title}:\n" + "\n".join(
        f"- {line}"
        for line in visible
    )

    if len(lines) > max_lines:
        result += (
            f"\n- ... ytterligare {len(lines) - max_lines} rader utelämnade"
        )

    return result


def bluetooth_status():
    """Lista Bluetooth-adaptrar och kända/anslutna enheter."""
    system = platform.system()

    try:
        if system == "Windows":
            result = _run_command(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "$OutputEncoding = "
                        "[Console]::OutputEncoding = "
                        "[System.Text.UTF8Encoding]::new(); "
                        "Get-PnpDevice -PresentOnly -Class Bluetooth | "
                        "Select-Object -ExpandProperty FriendlyName"
                    ),
                ],
                encoding="utf-8",
            )

        elif system == "Linux":
            result = _run_command(
                [
                    "bluetoothctl",
                    "devices",
                ]
            )

        elif system == "Darwin":
            result = _run_command(
                [
                    "system_profiler",
                    "SPBluetoothDataType",
                ]
            )

        else:
            return (
                "Bluetooth-status stöds ännu inte på operativsystemet "
                f"{system or 'okänt'}."
            )

        if result.returncode != 0:
            error_text = result.stderr.strip()

            if error_text:
                return f"Kunde inte läsa Bluetooth-status: {error_text}"

            return "Kunde inte läsa Bluetooth-status."

        return _format_lines(result.stdout)

    except FileNotFoundError:
        return (
            "Operativsystemets Bluetooth-verktyg hittades inte."
        )

    except subprocess.TimeoutExpired:
        return "Bluetooth-avläsningen tog för lång tid och avbröts."

    except Exception as error:
        return f"Fel vid Bluetooth-avläsning: {error}"


TOOLS = {
    "bluetooth_status": {
        "function": bluetooth_status,
        "description": (
            "Visar Bluetooth-adaptrar och kända eller anslutna "
            "Bluetooth-enheter utan att ändra anslutningar."
        ),
    }
}
