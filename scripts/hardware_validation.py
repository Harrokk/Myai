import json
from pathlib import Path
import platform
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.bluetooth.proximity import scan_nearby_devices
from modules.camera.camera import get_camera_inventory, format_camera_inventory
from modules.camera.capture import capture_from_settings, format_capture_result
from modules.camera.video import format_video_result, record_video_from_settings
from modules.camera.video_frames import (
    format_video_frame_result,
    sample_latest_video_from_settings,
)
from modules.hardware.hardware import (
    compare_hardware_snapshots,
    get_hardware_inventory,
)


REPORT_PATH = PROJECT_ROOT / "runtime" / "hardware_validation_report.json"


def record(results, name, status, details=""):
    item = {
        "name": name,
        "status": status,
        "details": details,
    }
    results.append(item)
    detail_text = f" - {details}" if details else ""
    print(f"[{status}] {name}{detail_text}")
    return item


def save_report(results):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with REPORT_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "results": results,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    return REPORT_PATH


def run_smoke_test(results):
    print()
    print("=" * 60)
    print("DEL 1 - MyAI smoke-test")
    print("=" * 60)

    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "smoke_test.py")],
        cwd=PROJECT_ROOT,
    )

    if completed.returncode == 0:
        record(results, "MyAI smoke-test", "PASS")
        return True

    record(
        results,
        "MyAI smoke-test",
        "FAIL",
        f"exit code {completed.returncode}",
    )
    return False


def inventory_check(results):
    print()
    print("=" * 60)
    print("DEL 2 - Hårdvaruinventering")
    print("=" * 60)

    try:
        devices = get_hardware_inventory()
    except Exception as error:
        record(results, "Hårdvaruinventering", "FAIL", str(error))
        return None

    if not devices:
        record(results, "Hårdvaruinventering", "FAIL", "0 enheter")
        return None

    record(
        results,
        "Hårdvaruinventering",
        "PASS",
        f"{len(devices)} enheter",
    )
    return devices


def physical_change_check(results, baseline):
    print()
    print("=" * 60)
    print("DEL 3 - Fysisk borttagning/återanslutning")
    print("=" * 60)
    print(
        "Använd Seagate-disken eller en annan tydlig USB-enhet. "
        "Baslinjen är redan tagen."
    )
    input("Koppla UR test-enheten, vänta tills Windows reagerat och tryck Enter: ")

    after_remove = get_hardware_inventory()
    removed_changes = compare_hardware_snapshots(
        baseline,
        after_remove,
    )

    removed = removed_changes["removed"]

    if removed:
        names = ", ".join(device["name"] for device in removed[:8])
        record(
            results,
            "Upptäckt av borttagen enhet",
            "PASS",
            names,
        )
    else:
        record(
            results,
            "Upptäckt av borttagen enhet",
            "FAIL",
            "Ingen borttagen enhet upptäcktes.",
        )

    input("Koppla IN test-enheten igen, vänta tills Windows reagerat och tryck Enter: ")

    after_add = get_hardware_inventory()
    added_changes = compare_hardware_snapshots(
        after_remove,
        after_add,
    )

    added = added_changes["added"]

    if added:
        names = ", ".join(device["name"] for device in added[:8])
        record(
            results,
            "Upptäckt av ny enhet",
            "PASS",
            names,
        )
    else:
        record(
            results,
            "Upptäckt av ny enhet",
            "FAIL",
            "Ingen ny enhet upptäcktes.",
        )

    return bool(removed) and bool(added)


def bluetooth_proximity_check(results):
    print()
    print("=" * 60)
    print("DEL 4 - Bluetooth LE / RSSI-närhet")
    print("=" * 60)
    print(
        "Se till att Bluetooth är aktiverat och att minst en BLE-enhet "
        "i närheten annonserar, till exempel hörlurar, telefon eller sensor."
    )
    input("Tryck Enter för att starta en 5-sekunders Bluetooth-skanning: ")

    try:
        observations = scan_nearby_devices(timeout=5.0)
    except Exception as error:
        record(
            results,
            "Bluetooth RSSI-skanning",
            "FAIL",
            str(error),
        )
        return False

    with_rssi = [
        item
        for item in observations
        if item.get("rssi") is not None
        and item.get("estimated_distance_m") is not None
    ]

    if not with_rssi:
        record(
            results,
            "Bluetooth RSSI-skanning",
            "FAIL",
            "Ingen BLE-enhet med användbart RSSI-värde upptäcktes.",
        )
        return False

    preview = ", ".join(
        f"{item['name']} ({item['rssi']} dBm, {item['proximity']})"
        for item in with_rssi[:5]
    )
    record(
        results,
        "Bluetooth RSSI-skanning",
        "PASS",
        preview,
    )
    return True


def camera_inventory_check(results):
    print()
    print("=" * 60)
    print("DEL 5 - Kamerainventering")
    print("=" * 60)

    try:
        devices = get_camera_inventory()
    except Exception as error:
        record(results, "Kamerainventering", "FAIL", str(error))
        return False

    print(format_camera_inventory(devices))

    if devices:
        record(
            results,
            "Kamerainventering",
            "PASS",
            f"{len(devices)} kamera/videoenheter upptäcktes",
        )
        return True

    record(
        results,
        "Kamerainventering",
        "WARN",
        "Ingen kamera upptäcktes; detta är okej om ingen kamera är ansluten.",
    )
    return True


def camera_capture_check(results):
    print()
    print("=" * 60)
    print("DEL 6 - Kamerastillbild")
    print("=" * 60)

    devices = get_camera_inventory()

    if not devices:
        record(
            results,
            "Kamerastillbild",
            "SKIP",
            "Ingen kamera upptäcktes.",
        )
        return True

    input(
        "Kontrollera att standardkameran är fri och tryck Enter "
        "för att ta en testbild: "
    )

    try:
        capture_result = capture_from_settings()
    except Exception as error:
        record(results, "Kamerastillbild", "FAIL", str(error))
        return False

    print(format_capture_result(capture_result))

    if not capture_result.get("success"):
        record(
            results,
            "Kamerastillbild",
            "FAIL",
            capture_result.get("error") or "okänt fel",
        )
        return False

    record(
        results,
        "Kamerastillbild",
        "PASS",
        (
            f"{capture_result.get('width')}x"
            f"{capture_result.get('height')} | kameraindex "
            f"{capture_result.get('camera_index')} -> "
            f"{capture_result.get('path')}"
        ),
    )
    return True


def camera_video_check(results):
    print()
    print("=" * 60)
    print("DEL 7 - Kort videoinspelning")
    print("=" * 60)

    devices = get_camera_inventory()

    if not devices:
        record(
            results,
            "Videoinspelning",
            "SKIP",
            "Ingen kamera upptäcktes.",
        )
        return True

    input(
        "Kontrollera att standardkameran är fri och tryck Enter "
        "för att spela in ett kort testklipp: "
    )

    try:
        video_result = record_video_from_settings()
    except Exception as error:
        record(results, "Videoinspelning", "FAIL", str(error))
        return False

    print(format_video_result(video_result))

    if not video_result.get("success"):
        record(
            results,
            "Videoinspelning",
            "FAIL",
            video_result.get("error") or "okänt fel",
        )
        return False

    record(
        results,
        "Videoinspelning",
        "PASS",
        (
            f"{video_result.get('frames')} bildrutor | "
            f"kameraindex {video_result.get('camera_index')} -> "
            f"{video_result.get('path')}"
        ),
    )
    return True


def camera_video_frame_sampling_check(results):
    print()
    print("=" * 60)
    print("DEL 8 - Representativa videobildrutor")
    print("=" * 60)

    try:
        frame_result = sample_latest_video_from_settings()
    except Exception as error:
        record(results, "Videobildrutor", "FAIL", str(error))
        return False

    print(format_video_frame_result(frame_result))

    if not frame_result.get("success"):
        record(
            results,
            "Videobildrutor",
            "FAIL",
            frame_result.get("error") or "okänt fel",
        )
        return False

    record(
        results,
        "Videobildrutor",
        "PASS",
        (
            f"{len(frame_result.get('frames', []))} bildrutor från "
            f"{frame_result.get('video_path')}"
        ),
    )
    return True


def main():
    results = []

    print("=" * 60)
    print("MyAI samlad hårdvaruverifiering")
    print("=" * 60)
    print(f"Plattform: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]}")
    print()

    smoke_ok = run_smoke_test(results)
    baseline = inventory_check(results)

    if baseline is not None:
        physical_change_check(results, baseline)
    else:
        record(
            results,
            "Fysisk förändringsdetektering",
            "SKIP",
            "Inventeringen måste fungera först.",
        )

    bluetooth_proximity_check(results)

    camera_inventory_check(results)

    camera_capture_check(results)

    camera_video_check(results)

    camera_video_frame_sampling_check(results)

    path = save_report(results)

    print()
    print("=" * 60)
    print("RESULTAT")
    print("=" * 60)

    for item in results:
        print(f"{item['status']}: {item['name']}")

    failures = [
        item
        for item in results
        if item["status"] == "FAIL"
    ]

    print()
    print(f"Rapport sparad: {path}")

    if failures:
        print(f"Verifieringen har {len(failures)} fel.")
        return 1

    if not smoke_ok:
        return 1

    print("Samtliga genomförda verifieringssteg är godkända.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
