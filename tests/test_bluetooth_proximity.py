from types import SimpleNamespace

from modules.bluetooth import proximity


def test_classify_proximity_uses_conservative_rssi_bands():
    assert proximity.classify_proximity(-45) == "mycket nära"
    assert proximity.classify_proximity(-58) == "nära"
    assert proximity.classify_proximity(-67) == "medel"
    assert proximity.classify_proximity(-76) == "långt bort"
    assert proximity.classify_proximity(-90) == "mycket svag signal"


def test_estimate_distance_is_monotonic_for_weaker_signal():
    near = proximity.estimate_distance_meters(-50)
    far = proximity.estimate_distance_meters(-75)

    assert near is not None
    assert far is not None
    assert near < far


def test_estimate_distance_prefers_advertised_tx_power():
    default_distance = proximity.estimate_distance_meters(-65)
    calibrated_distance = proximity.estimate_distance_meters(
        -65,
        tx_power=-50,
    )

    assert calibrated_distance != default_distance


def test_normalize_observation_uses_local_name_and_rssi():
    device = SimpleNamespace(
        name="Fallback name",
        address="AA:BB:CC:DD:EE:FF",
    )
    advertisement = SimpleNamespace(
        local_name="Beacon",
        rssi=-62,
        tx_power=-55,
    )

    result = proximity.normalize_observation(
        device,
        advertisement,
    )

    assert result["name"] == "Beacon"
    assert result["address"] == "AA:BB:CC:DD:EE:FF"
    assert result["rssi"] == -62
    assert result["proximity"] == "medel"
    assert result["estimated_distance_m"] is not None


def test_scan_nearby_devices_sorts_strongest_first(monkeypatch):
    weak_device = SimpleNamespace(
        name="Weak",
        address="02",
    )
    weak_adv = SimpleNamespace(
        local_name=None,
        rssi=-80,
        tx_power=None,
    )
    strong_device = SimpleNamespace(
        name="Strong",
        address="01",
    )
    strong_adv = SimpleNamespace(
        local_name=None,
        rssi=-45,
        tx_power=None,
    )

    async def fake_discover(timeout):
        assert timeout == 1.5
        return {
            "weak": (weak_device, weak_adv),
            "strong": (strong_device, strong_adv),
        }

    monkeypatch.setattr(
        proximity,
        "_discover_devices",
        fake_discover,
    )

    result = proximity.scan_nearby_devices(timeout=1.5)

    assert [item["name"] for item in result] == [
        "Strong",
        "Weak",
    ]


def test_format_nearby_devices_warns_about_rssi_limitations():
    result = proximity.format_nearby_devices(
        [
            {
                "name": "Test beacon",
                "rssi": -60,
                "proximity": "nära",
                "estimated_distance_m": 1.1,
            }
        ]
    )

    assert "Test beacon" in result
    assert "-60 dBm" in result
    assert "grov uppskattning" in result
    assert "påverkas starkt" in result


def test_bluetooth_nearby_handles_missing_bleak(monkeypatch):
    def missing(*args, **kwargs):
        raise ImportError("bleak saknas")

    monkeypatch.setattr(
        proximity,
        "scan_nearby_devices",
        missing,
    )

    result = proximity.bluetooth_nearby()

    assert "bleak" in result.lower()
