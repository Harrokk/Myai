import threading

from core.terminal_policy import (
    evaluate_terminal_connection,
    find_terminal_config,
)
from modules.bluetooth.proximity import scan_nearby_devices


class TerminalHandoffMonitor:
    def __init__(
        self,
        settings,
        scanner=None,
        connector=None,
        on_event=None,
        on_error=None,
    ):
        self.settings = settings
        self.config = settings.get(
            "trusted_terminals",
            {},
        )
        self.scanner = scanner or scan_nearby_devices
        self.connector = connector
        self.on_event = on_event
        self.on_error = on_error

        self.interval_seconds = max(
            1.0,
            float(
                self.config.get(
                    "scan_interval_seconds",
                    5.0,
                )
            ),
        )
        self.connect_confirm_scans = max(
            1,
            int(
                self.config.get(
                    "connect_confirm_scans",
                    2,
                )
            ),
        )
        self.disconnect_confirm_scans = max(
            1,
            int(
                self.config.get(
                    "disconnect_confirm_scans",
                    3,
                )
            ),
        )
        self.auto_execute = bool(
            self.config.get(
                "auto_execute",
                False,
            )
        )

        self._states = {}
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_running(self):
        return bool(
            self._thread
            and self._thread.is_alive()
        )

    def status(self):
        return {
            "enabled": bool(
                self.config.get(
                    "enabled",
                    False,
                )
            ),
            "running": self.is_running,
            "auto_execute": self.auto_execute,
            "scan_interval_seconds": self.interval_seconds,
            "connect_confirm_scans": self.connect_confirm_scans,
            "disconnect_confirm_scans": self.disconnect_confirm_scans,
            "tracked_terminals": {
                device_id: dict(state)
                for device_id, state in self._states.items()
            },
        }

    def start(self):
        if self.is_running:
            return False

        if not self.config.get(
            "enabled",
            False,
        ):
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="MyAI-TerminalHandoff",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, timeout=3.0):
        self._stop_event.set()

        thread = self._thread

        if (
            thread is not None
            and thread is not threading.current_thread()
        ):
            thread.join(
                timeout=max(
                    0.0,
                    float(timeout),
                )
            )

        return not self.is_running

    def _state_for(self, device_id):
        return self._states.setdefault(
            device_id,
            {
                "near_count": 0,
                "far_count": 0,
                "near_latched": False,
                "last_rssi": None,
                "last_seen": False,
                "last_action": None,
                "last_execution_success": None,
            },
        )

    def _configured_ids(self):
        return {
            terminal.get("id")
            for terminal in self.config.get(
                "terminals",
                [],
            )
            if terminal.get("id")
        }

    def _execute(self, action, device_id):
        if not self.auto_execute:
            return {
                "attempted": False,
                "success": None,
                "reason": (
                    "Automatisk connect/disconnect är avstängd; "
                    "endast rekommendation skapades."
                ),
            }

        if self.connector is None:
            return {
                "attempted": False,
                "success": False,
                "reason": (
                    "auto_execute är aktiverat men ingen connector är konfigurerad."
                ),
            }

        method = getattr(
            self.connector,
            action,
            None,
        )

        if not callable(method):
            return {
                "attempted": False,
                "success": False,
                "reason": (
                    f"Connector saknar metoden {action}."
                ),
            }

        try:
            result = method(device_id)

            if result is None:
                success = True
            elif isinstance(result, bool):
                success = result
            elif isinstance(result, dict):
                success = bool(
                    result.get(
                        "success",
                        False,
                    )
                )
            else:
                success = bool(result)

            return {
                "attempted": True,
                "success": success,
                "reason": (
                    "Connector kördes."
                    if success
                    else "Connector rapporterade misslyckande."
                ),
            }
        except Exception as error:
            return {
                "attempted": True,
                "success": False,
                "reason": str(error),
            }

    def _emit_event(
        self,
        action,
        observation,
        decision,
        state,
    ):
        device_id = (
            observation.get("id")
            or observation.get("address")
        )
        terminal = find_terminal_config(
            self.settings,
            device_id,
        ) or {}
        execution = self._execute(
            action,
            device_id,
        )

        event = {
            "action": action,
            "device_id": device_id,
            "name": (
                terminal.get("name")
                or terminal.get("label")
                or observation.get("name")
                or device_id
            ),
            "rssi": observation.get("rssi"),
            "estimated_distance_m": observation.get(
                "estimated_distance_m"
            ),
            "policy_reason": decision.get(
                "reason"
            ),
            "executed": execution["attempted"],
            "execution_success": execution["success"],
            "execution_reason": execution["reason"],
            "proximity_state": (
                "near"
                if action == "connect"
                else "far"
            ),
        }
        state["last_action"] = action
        state["last_execution_success"] = execution["success"]

        if self.on_event is not None:
            self.on_event(event)

        return event

    def poll_once(self):
        if not self.config.get(
            "enabled",
            False,
        ):
            return []

        observations = self.scanner(
            timeout=self.config.get(
                "scan_timeout_seconds",
                5.0,
            )
        )
        by_id = {
            (
                item.get("id")
                or item.get("address")
            ): item
            for item in observations
            if (
                item.get("id")
                or item.get("address")
            )
        }

        events = []
        configured_ids = self._configured_ids()

        for device_id in configured_ids:
            terminal = find_terminal_config(
                self.settings,
                device_id,
            )

            if not terminal:
                continue

            state = self._state_for(
                device_id
            )
            observation = by_id.get(
                device_id
            )

            if observation is None:
                state["last_seen"] = False
                state["last_rssi"] = None
                state["near_count"] = 0

                if state["near_latched"]:
                    state["far_count"] += 1

                    if (
                        state["far_count"]
                        >= self.disconnect_confirm_scans
                    ):
                        synthetic = {
                            "id": device_id,
                            "name": (
                                terminal.get("name")
                                or terminal.get("label")
                                or device_id
                            ),
                            "rssi": None,
                            "estimated_distance_m": None,
                        }
                        decision = {
                            "action": "disconnect",
                            "allowed": True,
                            "reason": (
                                "Terminalen saknades i "
                                f"{state['far_count']} efterföljande skanningar."
                            ),
                        }
                        events.append(
                            self._emit_event(
                                "disconnect",
                                synthetic,
                                decision,
                                state,
                            )
                        )
                        state["near_latched"] = False
                        state["far_count"] = 0

                continue

            state["last_seen"] = True
            state["last_rssi"] = observation.get(
                "rssi"
            )

            decision = evaluate_terminal_connection(
                observation,
                self.settings,
                is_connected=state[
                    "near_latched"
                ],
            )
            action = decision.get("action")

            if action == "connect":
                state["near_count"] += 1
                state["far_count"] = 0

                if (
                    not state["near_latched"]
                    and state["near_count"]
                    >= self.connect_confirm_scans
                ):
                    events.append(
                        self._emit_event(
                            "connect",
                            observation,
                            decision,
                            state,
                        )
                    )
                    state["near_latched"] = True
                    state["near_count"] = 0

            elif action == "disconnect":
                state["far_count"] += 1
                state["near_count"] = 0

                if (
                    state["near_latched"]
                    and state["far_count"]
                    >= self.disconnect_confirm_scans
                ):
                    events.append(
                        self._emit_event(
                            "disconnect",
                            observation,
                            decision,
                            state,
                        )
                    )
                    state["near_latched"] = False
                    state["far_count"] = 0

            elif action == "keep":
                state["near_count"] = 0
                state["far_count"] = 0

            else:
                if not state["near_latched"]:
                    state["near_count"] = 0

        return events

    def _run(self):
        while not self._stop_event.wait(
            self.interval_seconds
        ):
            try:
                self.poll_once()
            except Exception as error:
                if self.on_error is not None:
                    self.on_error(error)


def format_terminal_handoff_event(event):
    action = event.get(
        "action",
        "unknown",
    )
    action_text = {
        "connect": "Anslutningsläge",
        "disconnect": "Frånkopplingsläge",
    }.get(
        action,
        action,
    )
    rssi = event.get("rssi")
    rssi_text = (
        f"{rssi} dBm"
        if rssi is not None
        else "RSSI saknas"
    )
    distance = event.get(
        "estimated_distance_m"
    )
    distance_text = (
        f", ca {distance:.2f} m"
        if distance is not None
        else ""
    )
    mode = (
        "utfört"
        if (
            event.get("executed")
            and event.get(
                "execution_success"
            )
        )
        else "rekommendation"
    )

    return (
        f"{action_text}: {event.get('name')} | "
        f"{rssi_text}{distance_text} | {mode}. "
        f"{event.get('policy_reason') or ''}"
    ).strip()
