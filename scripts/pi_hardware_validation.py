import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.pi.interfaces import collect_pi_interfaces, format_pi_interfaces
from modules.pi.system_status import collect_pi_status, format_pi_status


REPORT_PATH = PROJECT_ROOT / "runtime" / "pi_hardware_validation_report.json"


def record(results, name, status, details=""):
    item = {
        "name": name,
        "status": status,
        "details": details,
    }
    results.append(item)
    detail_text = f" - {details}" if details else ""
    print(f"[{status}] {name}{detail_text}")


def main():
    results = []

    print("=" * 60)
    print("MyAI Raspberry Pi hårdvaruverifiering")
    print("=" * 60)

    status = collect_pi_status()
    print()
    print(format_pi_status(status))
    print()

    if not status.get("is_raspberry_pi"):
        record(
            results,
            "Raspberry Pi-detektering",
            "FAIL",
            status.get("model") or "ingen modell identifierad",
        )
    else:
        record(
            results,
            "Raspberry Pi-detektering",
            "PASS",
            status.get("model") or "modell okänd",
        )

        temperature = status.get("temperature_c")
        record(
            results,
            "CPU-temperatur",
            "PASS" if temperature is not None else "FAIL",
            f"{temperature:.1f} °C" if temperature is not None else "saknas",
        )

        throttling = status.get("throttling")

        if throttling is None:
            record(
                results,
                "Throttling/underspänning",
                "WARN",
                "vcgencmd-data kunde inte läsas",
            )
        else:
            current_mask = throttling["raw"] & 0xF
            record(
                results,
                "Throttling/underspänning",
                "FAIL" if current_mask else "PASS",
                (
                    ", ".join(throttling["flags"])
                    if throttling["flags"]
                    else "inga flaggor"
                ),
            )

        voltage = status.get("core_voltage_v")
        record(
            results,
            "Kärnspänning",
            "PASS" if voltage is not None else "WARN",
            f"{voltage:.3f} V" if voltage is not None else "kunde inte läsas",
        )

    interface_result = collect_pi_interfaces()
    print()
    print(format_pi_interfaces(interface_result))
    print()

    if not interface_result.get("supported"):
        record(
            results,
            "Pi-gränssnitt",
            "FAIL",
            "Linux/Raspberry Pi krävs för gränssnittsinventering",
        )
    else:
        found = sum(
            len(items)
            for items in interface_result.get("interfaces", {}).values()
        )
        record(
            results,
            "Pi-gränssnitt",
            "PASS" if found else "WARN",
            f"{found} enhetsnoder hittades",
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "status": status,
                "interfaces": interface_result,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Rapport sparad: {REPORT_PATH}")

    failures = [item for item in results if item["status"] == "FAIL"]

    if failures:
        print(f"Verifieringen har {len(failures)} fel.")
        return 1

    print("Raspberry Pi-verifieringen är godkänd.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
