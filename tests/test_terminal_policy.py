from core.terminal_policy import evaluate_terminal_connection


def settings():
    return {
        "trusted_terminals": {
            "enabled": True,
            "connect_rssi": -60,
            "disconnect_rssi": -75,
            "terminals": [
                {
                    "id": "car-terminal",
                    "trusted": True,
                    "auto_connect": True,
                }
            ],
        }
    }


def test_unknown_terminal_never_auto_connects():
    result = evaluate_terminal_connection(
        {"id": "unknown", "rssi": -40},
        settings(),
    )
    assert result["action"] == "none"
    assert result["allowed"] is False


def test_trusted_terminal_connects_inside_threshold():
    result = evaluate_terminal_connection(
        {"id": "car-terminal", "rssi": -55},
        settings(),
    )
    assert result["action"] == "connect"
    assert result["allowed"] is True


def test_trusted_terminal_does_not_connect_when_too_far():
    result = evaluate_terminal_connection(
        {"id": "car-terminal", "rssi": -70},
        settings(),
    )
    assert result["action"] == "none"
    assert result["allowed"] is False


def test_connected_terminal_uses_hysteresis():
    keep = evaluate_terminal_connection(
        {"id": "car-terminal", "rssi": -70},
        settings(),
        is_connected=True,
    )
    disconnect = evaluate_terminal_connection(
        {"id": "car-terminal", "rssi": -80},
        settings(),
        is_connected=True,
    )

    assert keep["action"] == "keep"
    assert disconnect["action"] == "disconnect"


def test_missing_rssi_never_connects():
    result = evaluate_terminal_connection(
        {"id": "car-terminal", "rssi": None},
        settings(),
    )
    assert result["action"] == "none"
    assert result["allowed"] is False


def test_terminal_can_override_global_thresholds():
    custom = settings()
    custom["trusted_terminals"]["terminals"][0]["connect_rssi"] = -50
    custom["trusted_terminals"]["terminals"][0]["disconnect_rssi"] = -70

    result = evaluate_terminal_connection(
        {"id": "car-terminal", "rssi": -55},
        custom,
    )

    assert result["action"] == "none"


def test_invalid_rssi_never_authorizes_bluetooth_connect():
    for rssi in (0, 1, -129, True, False, float("nan"),
                 float("inf"), float("-inf"), "0", "-40", {}, []):
        decision = evaluate_terminal_connection(
            {"id": "car-terminal", "rssi": rssi},
            settings(),
        )
        assert decision["action"] == "none", repr(rssi)
        assert decision["allowed"] is False, repr(rssi)


def test_invalid_rssi_never_claims_connected_device_is_near():
    for rssi in (0, float("nan"), "bad", True):
        decision = evaluate_terminal_connection(
            {"id": "car-terminal", "rssi": rssi},
            settings(),
            is_connected=True,
        )
        assert decision["action"] == "none"


def test_corrupt_terminal_thresholds_fail_closed():
    for bad in (None, "very strong", float("nan"), True, 0):
        current = settings()
        current["trusted_terminals"]["terminals"][0]["connect_rssi"] = bad
        result = evaluate_terminal_connection(
            {"id": "car-terminal", "rssi": -45},
            current,
        )
        assert result["action"] == "none", repr(bad)
        assert result["allowed"] is False, repr(bad)


def test_valid_finite_float_rssi_is_allowed():
    decision = evaluate_terminal_connection(
        {"id": "car-terminal", "rssi": -55.0},
        settings(),
    )
    assert decision["action"] == "connect"
    assert decision["allowed"] is True
