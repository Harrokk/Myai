import shutil
import subprocess
from pathlib import Path

import psutil


def gpu_status():
    try:
        executable = shutil.which(
            "nvidia-smi"
        )

        if executable is None:
            return (
                "NVIDIA GPU-status är inte tillgänglig på denna plattform. "
                "Integrerade AI-acceleratorer hanteras av sina egna providers."
            )

        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return "Kunde inte läsa GPU-status."

        data = result.stdout.strip()

        if not data:
            return "Ingen GPU-information hittades."

        parts = [
            value.strip()
            for value in data.split(",")
        ]

        if len(parts) < 5:
            return (
                f"GPU-information: {data}"
            )

        name = parts[0]
        memory_used = parts[1]
        memory_total = parts[2]
        utilization = parts[3]
        temperature = parts[4]

        return (
            f"GPU: {name}\n"
            f"VRAM: {memory_used} MiB / {memory_total} MiB\n"
            f"GPU-belastning: {utilization}%\n"
            f"Temperatur: {temperature} °C"
        )

    except Exception as error:
        return (
            f"Fel vid GPU-avläsning: {error}"
        )


def cpu_status():
    try:
        cpu_usage = psutil.cpu_percent(
            interval=1
        )
        cpu_count = psutil.cpu_count(
            logical=True
        )

        return (
            f"CPU-belastning: {cpu_usage}%\n"
            f"Logiska CPU-kärnor: {cpu_count}"
        )

    except Exception as error:
        return (
            f"Fel vid CPU-avläsning: {error}"
        )


def ram_status():
    try:
        memory = psutil.virtual_memory()

        used_gb = (
            memory.used
            / (1024 ** 3)
        )
        total_gb = (
            memory.total
            / (1024 ** 3)
        )

        return (
            f"RAM: {used_gb:.1f} GB / "
            f"{total_gb:.1f} GB\n"
            f"RAM-belastning: "
            f"{memory.percent}%"
        )

    except Exception as error:
        return (
            f"Fel vid RAM-avläsning: {error}"
        )


def _linux_thermal_zones(
    base_path=Path(
        "/sys/class/thermal"
    ),
):
    results = []

    try:
        zones = sorted(
            base_path.glob(
                "thermal_zone*"
            )
        )
    except OSError:
        return results

    for zone in zones:
        try:
            raw = (
                zone
                .joinpath("temp")
                .read_text(
                    encoding="utf-8"
                )
                .strip()
            )
            value = float(raw)

            if abs(value) > 1000:
                value /= 1000.0

            label_path = (
                zone
                / "type"
            )
            label = (
                label_path.read_text(
                    encoding="utf-8"
                ).strip()
                if label_path.exists()
                else zone.name
            )

            if (
                -50.0
                <= value
                <= 200.0
            ):
                results.append(
                    (
                        label
                        or zone.name,
                        value,
                    )
                )
        except (
            OSError,
            ValueError,
        ):
            continue

    return results


def temperature_status():
    results = []
    seen = set()

    executable = shutil.which(
        "nvidia-smi"
    )

    if executable is not None:
        try:
            gpu_result = subprocess.run(
                [
                    executable,
                    "--query-gpu=name,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if gpu_result.returncode == 0:
                data = (
                    gpu_result.stdout
                    .strip()
                )

                for line in data.splitlines():
                    parts = [
                        value.strip()
                        for value
                        in line.split(",")
                    ]

                    if len(parts) >= 2:
                        text = (
                            f"GPU ({parts[0]}): "
                            f"{parts[1]} °C"
                        )

                        if text not in seen:
                            seen.add(text)
                            results.append(
                                text
                            )
        except Exception:
            pass

    try:
        if hasattr(
            psutil,
            "sensors_temperatures",
        ):
            temperatures = (
                psutil
                .sensors_temperatures()
                or {}
            )

            for name, entries in (
                temperatures.items()
            ):
                for entry in entries:
                    label = (
                        entry.label
                        if entry.label
                        else name
                    )
                    text = (
                        f"{label}: "
                        f"{entry.current} °C"
                    )

                    if text not in seen:
                        seen.add(text)
                        results.append(
                            text
                        )
    except Exception:
        pass

    if not results:
        for label, value in (
            _linux_thermal_zones()
        ):
            text = (
                f"{label}: "
                f"{value:.1f} °C"
            )

            if text not in seen:
                seen.add(text)
                results.append(
                    text
                )

    if results:
        return "\n".join(
            results
        )

    return (
        "Inga temperaturvärden "
        "kunde läsas."
    )


def _project_disk_root():
    anchor = (
        Path(__file__)
        .resolve()
        .anchor
    )

    return anchor or "/"


def disk_status():
    try:
        path = _project_disk_root()
        disk = psutil.disk_usage(
            path
        )

        used_gb = (
            disk.used
            / (1024 ** 3)
        )
        total_gb = (
            disk.total
            / (1024 ** 3)
        )
        free_gb = (
            disk.free
            / (1024 ** 3)
        )

        return (
            f"Disk {path}\n"
            f"Använt: {used_gb:.1f} GB\n"
            f"Ledigt: {free_gb:.1f} GB\n"
            f"Totalt: {total_gb:.1f} GB\n"
            f"Användning: {disk.percent}%"
        )

    except Exception as error:
        return (
            f"Fel vid diskläsning: {error}"
        )


TOOLS = {
    "gpu_status": {
        "function": gpu_status,
        "description": (
            "Visar NVIDIA GPU-status när nvidia-smi finns; "
            "integrerade acceleratorer hanteras separat."
        ),
    },
    "cpu_status": {
        "function": cpu_status,
        "description": (
            "Visar CPU-belastning och antal logiska CPU-kärnor."
        ),
    },
    "ram_status": {
        "function": ram_status,
        "description": (
            "Visar RAM-användning och total mängd RAM."
        ),
    },
    "temperature_status": {
        "function": temperature_status,
        "description": (
            "Kontrollerar tillgängliga temperaturer "
            "via GPU, psutil eller Linux thermal sysfs."
        ),
    },
    "disk_status": {
        "function": disk_status,
        "description": (
            "Visar ledigt lagringsutrymme på filsystemet "
            "där MyAI-koden körs."
        ),
    },
}
