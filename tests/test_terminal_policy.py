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
