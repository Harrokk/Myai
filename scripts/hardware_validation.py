import json
from pathlib import Path
import platform
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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
