from core.terminal_handoff import (
    TerminalHandoffMonitor,
    format_terminal_handoff_event,
)


def settings(
    enabled=True,
    auto_execute=False,
):
    return {
        "trusted_terminals": {
            "enabled": enabled,
            "connect_rssi": -60,
            "disconnect_rssi": -75,
            "scan_interval_seconds": 5,
            "scan_timeout_seconds": 1,
            "connect_confirm_scans": 2,
            "disconnect_confirm_scans": 3,
            "auto_execute": auto_execute,
            "terminals": [
                {
                    "id": "car-terminal",
                    "name": "Bilterminal",
                    "trusted": True,
                    "auto_connect": True,
                }
            ],
        }
    }


def observation(
    rssi=-55,
    device_id="car-terminal",
):
    return {
        "id": device_id,
        "name": "Bilterminal",
        "rssi": rssi,
        "estimated_distance_m": 0.8,
    }


class SequenceScanner:
    def __init__(self, scans):
        self.scans = list(scans)
        self.calls = []

    def __call__(self, timeout):
        self.calls.append(timeout)

        if not self.scans:
            return []

        return self.scans.pop(0)


class FakeConnector:
    def __init__(self):
        self.connected = []
        self.disconnected = []

    def connect(self, device_id):
        self.connected.append(
            device_id
        )
        return True

    def disconnect(self, device_id):
        self.disconnected.append(
            device_id
        )
        return True


def test_disabled_monitor_does_not_poll():
    scanner = SequenceScanner(
        [[observation()]]
    )
    monitor = TerminalHandoffMonitor(
        settings(enabled=False),
        scanner=scanner,
    )

    assert monitor.poll_once() == []
    assert scanner.calls == []
    assert monitor.start() is False


def test_connect_requires_multiple_strong_scans():
    scanner = SequenceScanner(
        [
            [observation(-55)],
            [observation(-54)],
        ]
    )
    events = []
    monitor = TerminalHandoffMonitor(
        settings(),
        scanner=scanner,
        on_event=events.append,
    )

    assert monitor.poll_once() == []
    second = monitor.poll_once()

    assert len(second) == 1
    assert second[0]["action"] == "connect"
    assert second[0]["executed"] is False
    assert len(events) == 1


def test_hysteresis_keeps_terminal_latched_in_middle_band():
    scanner = SequenceScanner(
        [
            [observation(-55)],
            [observation(-55)],
            [observation(-68)],
            [observation(-70)],
        ]
    )
    monitor = TerminalHandoffMonitor(
        settings(),
        scanner=scanner,
    )

    monitor.poll_once()
    assert monitor.poll_once()[0]["action"] == "connect"
    assert monitor.poll_once() == []
    assert monitor.poll_once() == []

    state = monitor.status()[
        "tracked_terminals"
    ]["car-terminal"]
    assert state["near_latched"] is True


def test_disconnect_requires_multiple_weak_scans():
    scanner = SequenceScanner(
        [
            [observation(-55)],
            [observation(-55)],
            [observation(-80)],
            [observation(-81)],
            [observation(-82)],
        ]
    )
    monitor = TerminalHandoffMonitor(
        settings(),
        scanner=scanner,
    )

    monitor.poll_once()
    monitor.poll_once()
    assert monitor.poll_once() == []
    assert monitor.poll_once() == []
    events = monitor.poll_once()

    assert len(events) == 1
    assert events[0]["action"] == "disconnect"


def test_missing_terminal_counts_toward_disconnect():
    scanner = SequenceScanner(
        [
            [observation(-55)],
            [observation(-55)],
            [],
            [],
            [],
        ]
    )
    monitor = TerminalHandoffMonitor(
        settings(),
        scanner=scanner,
    )

    monitor.poll_once()
    monitor.poll_once()
    monitor.poll_once()
    monitor.poll_once()
    events = monitor.poll_once()

    assert len(events) == 1
    assert events[0]["action"] == "disconnect"
    assert events[0]["rssi"] is None


def test_unknown_device_is_ignored():
    scanner = SequenceScanner(
        [
            [observation(-40, "unknown")],
            [observation(-40, "unknown")],
        ]
    )
    monitor = TerminalHandoffMonitor(
        settings(),
        scanner=scanner,
    )

    assert monitor.poll_once() == []
    assert monitor.poll_once() == []
    assert monitor.status()[
        "tracked_terminals"
    ]["car-terminal"]["near_latched"] is False


def test_auto_execute_calls_connector():
    scanner = SequenceScanner(
        [
            [observation(-55)],
            [observation(-55)],
        ]
    )
    connector = FakeConnector()
    monitor = TerminalHandoffMonitor(
        settings(auto_execute=True),
        scanner=scanner,
        connector=connector,
    )

    monitor.poll_once()
    event = monitor.poll_once()[0]

    assert event["executed"] is True
    assert event["execution_success"] is True
    assert connector.connected == [
        "car-terminal"
    ]


def test_auto_execute_without_connector_fails_closed():
    scanner = SequenceScanner(
        [
            [observation(-55)],
            [observation(-55)],
        ]
    )
    monitor = TerminalHandoffMonitor(
        settings(auto_execute=True),
        scanner=scanner,
        connector=None,
    )

    monitor.poll_once()
    event = monitor.poll_once()[0]

    assert event["executed"] is False
    assert event["execution_success"] is False
    assert "ingen connector" in event[
        "execution_reason"
    ]


def test_format_event_reports_recommendation():
    text = format_terminal_handoff_event(
        {
            "action": "connect",
            "name": "Bilterminal",
            "rssi": -55,
            "estimated_distance_m": 0.8,
            "executed": False,
            "execution_success": None,
            "policy_reason": "Tillräckligt nära.",
        }
    )

    assert "Bilterminal" in text
    assert "-55 dBm" in text
    assert "rekommendation" in text
