import json
from pathlib import Path
import platform
import subprocess


LINUX_VIDEO_ROOT = Path("/sys/class/video4linux")


def _run(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def _normalize_windows_json(text):
    text = (text or "").strip()

    if not text:
        return []

    payload = json.loads(text)

    if isinstance(payload, dict):
        payload = [payload]

    if not isinstance(payload, list):
        return []

    devices = []

    for item in payload:
        if not isinstance(item, dict):
            continue

        name = (
            item.get("FriendlyName")
            or item.get("Name")
            or "Okänd kamera"
        )
        devices.append(
            {
                "category": item.get("Class") or "Camera",
                "name": name,
                "id": item.get("InstanceId") or name,
                "status": item.get("Status") or "",
                "source": "windows-pnp",
            }
        )

    return devices


def _windows_cameras():
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "$OutputEncoding = [Console]::OutputEncoding = "
            "[System.Text.Encoding]::UTF8; "
            "Get-PnpDevice -PresentOnly | "
            "Where-Object { $_.Class -eq 'Camera' -or $_.Class -eq 'Image' } | "
            "Select-Object Class,FriendlyName,InstanceId,Status | "
            "ConvertTo-Json -Compress"
        ),
    ]

    result = _run(command)

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or "PowerShell kunde inte läsa kameraenheter."
        )

    return _normalize_windows_json(result.stdout)


def _linux_cameras():
    devices = []

    if LINUX_VIDEO_ROOT.exists():
        entries = sorted(
            LINUX_VIDEO_ROOT.glob("video*"),
            key=lambda path: path.name,
        )

        for entry in entries:
            try:
                name = (entry / "name").read_text(
                    encoding="utf-8"
                ).strip()
            except (OSError, UnicodeError):
                name = entry.name

            devices.append(
                {
                    "category": "Camera",
                    "name": name or entry.name,
                    "id": f"/dev/{entry.name}",
                    "status": "present",
                    "source": "linux-video4linux",
                }
            )

        return devices

    for device in sorted(Path("/dev").glob("video*")):
        devices.append(
            {
                "category": "Camera",
                "name": device.name,
                "id": str(device),
                "status": "present",
                "source": "linux-video4linux",
            }
        )

    return devices


def get_camera_inventory():
    system = platform.system().lower()

    if system == "windows":
        return _windows_cameras()

    if system == "linux":
        return _linux_cameras()

    return []


def format_camera_inventory(devices):
    if not devices:
        return "Inga kameror eller Video4Linux-enheter upptäcktes."

    lines = [f"Kameror upptäckta: {len(devices)}"]

    for device in devices:
        status = device.get("status")
        status_text = f" [{status}]" if status else ""
        lines.append(
            f"- {device.get('name') or 'Okänd kamera'}"
            f"{status_text} | id={device.get('id') or 'saknas'}"
        )

    return "\n".join(lines)


def camera_status():
    try:
        return format_camera_inventory(get_camera_inventory())
    except Exception as error:
        return f"Fel vid kamerainventering: {error}"


TOOLS = {
    "camera_status": {
        "function": camera_status,
        "description": (
            "Inventerar read-only anslutna kameror/videoenheter på "
            "Windows eller Linux."
        ),
    }
}
