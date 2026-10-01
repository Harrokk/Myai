import subprocess
import psutil


def gpu_status():
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return "Kunde inte läsa GPU-status."

        data = result.stdout.strip()

        if not data:
            return "Ingen GPU-information hittades."

        parts = [x.strip() for x in data.split(",")]

        if len(parts) < 5:
            return f"GPU-information: {data}"

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

    except FileNotFoundError:
        return "nvidia-smi hittades inte."

    except Exception as error:
        return f"Fel vid GPU-avläsning: {error}"


def cpu_status():
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count(logical=True)

        return (
            f"CPU-belastning: {cpu_usage}%\n"
            f"Logiska CPU-kärnor: {cpu_count}"
        )

    except Exception as error:
        return f"Fel vid CPU-avläsning: {error}"


def ram_status():
    try:
        memory = psutil.virtual_memory()

        used_gb = memory.used / (1024 ** 3)
        total_gb = memory.total / (1024 ** 3)

        return (
            f"RAM: {used_gb:.1f} GB / {total_gb:.1f} GB\n"
            f"RAM-belastning: {memory.percent}%"
        )

    except Exception as error:
        return f"Fel vid RAM-avläsning: {error}"
def temperature_status():
    results = []

    # GPU-temperatur via nvidia-smi
    try:
        gpu_result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if gpu_result.returncode == 0:
            data = gpu_result.stdout.strip()

            if data:
                for line in data.splitlines():
                    parts = [x.strip() for x in line.split(",")]

                    if len(parts) >= 2:
                        results.append(
                            f"GPU ({parts[0]}): {parts[1]} °C"
                        )

    except Exception:
        pass

    # Försök läsa övriga temperatursensorer via psutil.
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temperatures = psutil.sensors_temperatures()

            for name, entries in temperatures.items():
                for entry in entries:
                    label = entry.label if entry.label else name

                    results.append(
                        f"{label}: {entry.current} °C"
                    )

    except Exception:
        pass

    if results:
        return "\n".join(results)

    return "Inga temperaturvärden kunde läsas."

def disk_status():
    try:
        disk = psutil.disk_usage("F:\\")

        used_gb = disk.used / (1024 ** 3)
        total_gb = disk.total / (1024 ** 3)
        free_gb = disk.free / (1024 ** 3)

        return (
            f"Disk F:\\\n"
            f"Använt: {used_gb:.1f} GB\n"
            f"Ledigt: {free_gb:.1f} GB\n"
            f"Totalt: {total_gb:.1f} GB\n"
            f"Användning: {disk.percent}%"
        )

    except Exception as error:
        return f"Fel vid diskläsning: {error}"
TOOLS = {
    "gpu_status": {
        "function": gpu_status,
        "description": "Visar status för NVIDIA-grafikkortet, inklusive belastning, temperatur och VRAM."
    },

    "cpu_status": {
        "function": cpu_status,
        "description": "Visar CPU-belastning och antal logiska CPU-kärnor."
    },

    "ram_status": {
        "function": ram_status,
        "description": "Visar RAM-användning och total mängd RAM."
    },

    "temperature_status": {
        "function": temperature_status,
        "description": "Kontrollerar temperaturer i datorn."
    },

    "disk_status": {
        "function": disk_status,
        "description": "Visar information om disk och ledigt lagringsutrymme."
    }
}