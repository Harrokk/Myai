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


def _format_lines(output, max_lines=50):
    lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip()
    ]

    if not lines:
        return "Inga USB-enheter hittades."

    visible = lines[:max_lines]
    result = "USB-enheter:\n" + "\n".join(
        f"- {line}"
        for line in visible
    )

    if len(lines) > max_lines:
        result += (
            f"\n- ... ytterligare {len(lines) - max_lines} rader utelämnade"
        )

    return result


def usb_status():
    """Lista anslutna USB-enheter med operativsystemets egna verktyg."""
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
                        "Get-PnpDevice -PresentOnly | "
                        "Where-Object { $_.InstanceId -match '^USB' } | "
                        "Select-Object -ExpandProperty FriendlyName"
                    ),
                ],
                encoding="utf-8",
            )

        elif system == "Linux":
            result = _run_command(["lsusb"])

        elif system == "Darwin":
            result = _run_command(
                ["system_profiler", "SPUSBDataType"]
            )

        else:
            return (
                f"USB-status stöds ännu inte på operativsystemet "
                f"{system or 'okänt'}."
            )

        if result.returncode != 0:
            error_text = result.stderr.strip()

            if error_text:
                return f"Kunde inte läsa USB-status: {error_text}"

            return "Kunde inte läsa USB-status."

        return _format_lines(result.stdout)

    except FileNotFoundError:
        return (
            "Operativsystemets verktyg för att läsa USB-enheter "
            "hittades inte."
        )

    except subprocess.TimeoutExpired:
        return "USB-avläsningen tog för lång tid och avbröts."

    except Exception as error:
        return f"Fel vid USB-avläsning: {error}"


TOOLS = {
    "usb_status": {
        "function": usb_status,
        "description": (
            "Visar anslutna USB-enheter och tillgänglig "
            "USB-information från operativsystemet."
        ),
    }
}
