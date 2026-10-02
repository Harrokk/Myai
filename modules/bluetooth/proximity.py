import asyncio
import math


DEFAULT_SCAN_SECONDS = 5.0
DEFAULT_TX_POWER_DBM = -59
DEFAULT_PATH_LOSS_EXPONENT = 2.2


def estimate_distance_meters(
    rssi,
    tx_power=None,
    path_loss_exponent=DEFAULT_PATH_LOSS_EXPONENT,
):
    """Grov RSSI-baserad avståndsuppskattning i meter."""
    if rssi is None:
        return None

    rssi = int(rssi)

    if rssi == 0:
        return None

    if path_loss_exponent <= 0:
        raise ValueError("path_loss_exponent måste vara större än 0")

    reference_power = (
        int(tx_power)
        if tx_power is not None
        else DEFAULT_TX_POWER_DBM
    )

    distance = 10 ** (
        (reference_power - rssi)
        / (10 * path_loss_exponent)
    )
    return round(distance, 2)


def classify_proximity(rssi):
    """Klassificera RSSI till en försiktig närhetsnivå."""
    if rssi is None:
        return "okänd"

    rssi = int(rssi)

    if rssi >= -50:
        return "mycket nära"
    if rssi >= -60:
        return "nära"
    if rssi >= -70:
        return "medel"
    if rssi >= -80:
        return "långt bort"
    return "mycket svag signal"


def normalize_observation(device, advertisement):
    """Normalisera Bleak-data utan att läcka backenddetaljer."""
    name = (
        getattr(advertisement, "local_name", None)
        or getattr(device, "name", None)
        or "Okänd Bluetooth-enhet"
    )
    rssi = getattr(advertisement, "rssi", None)
    tx_power = getattr(advertisement, "tx_power", None)
    address = getattr(device, "address", None)

    return {
        "id": address or name,
        "name": name,
        "address": address,
        "rssi": rssi,
        "tx_power": tx_power,
        "proximity": classify_proximity(rssi),
        "estimated_distance_m": estimate_distance_meters(
            rssi,
            tx_power=tx_power,
        ),
    }


async def _discover_devices(timeout):
    from bleak import BleakScanner

    return await BleakScanner.discover(
        timeout=timeout,
        return_adv=True,
    )


def scan_nearby_devices(timeout=DEFAULT_SCAN_SECONDS):
    """Skanna BLE-enheter och returnera normaliserade observationer."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        discovered = asyncio.run(_discover_devices(timeout))
    else:
        raise RuntimeError(
            "Bluetooth-skanning kan inte startas synkront inuti "
            "en redan aktiv asyncio-loop."
        )

    observations = [
        normalize_observation(device, advertisement)
        for device, advertisement in discovered.values()
    ]

    observations.sort(
        key=lambda item: (
            item["rssi"] is None,
            -(item["rssi"] or -999),
            item["name"].lower(),
        )
    )
    return observations


def format_nearby_devices(observations):
    if not observations:
        return (
            "Inga annonserande Bluetooth LE-enheter hittades under "
            "skanningen."
        )

    lines = [
        "Bluetooth-enheter i närheten "
        "(RSSI-baserad grov uppskattning):"
    ]

    for item in observations:
        rssi_text = (
            f"{item['rssi']} dBm"
            if item["rssi"] is not None
            else "RSSI saknas"
        )
        distance = item["estimated_distance_m"]
        distance_text = (
            f"ca {distance:.2f} m"
            if distance is not None
            else "avstånd okänt"
        )
        lines.append(
            f"- {item['name']}: {rssi_text}, "
            f"{item['proximity']}, {distance_text}"
        )

    lines.append(
        "Obs: Bluetooth-RSSI påverkas starkt av kroppar, väggar, "
        "antenner och radiomiljö. Meterangivelsen är en grov uppskattning."
    )
    return "\n".join(lines)


def bluetooth_nearby():
    """Skanna annonserande BLE-enheter och uppskatta grov närhet."""
    try:
        observations = scan_nearby_devices()
        return format_nearby_devices(observations)
    except ImportError:
        return (
            "Bluetooth-närhet kräver paketet bleak. "
            "Installera projektets requirements och försök igen."
        )
    except Exception as error:
        return f"Bluetooth-närhet kunde inte läsas: {error}"


TOOLS = {
    "bluetooth_nearby": {
        "function": bluetooth_nearby,
        "description": (
            "Skannar annonserande Bluetooth LE-enheter, läser RSSI och "
            "ger en grov uppskattning av närhet eller avstånd."
        ),
    }
}
