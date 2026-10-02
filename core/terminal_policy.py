DEFAULT_CONNECT_RSSI = -60
DEFAULT_DISCONNECT_RSSI = -75


def _terminal_settings(settings):
    return settings.get("trusted_terminals", {})


def find_terminal_config(settings, device_id):
    terminals = _terminal_settings(settings).get("terminals", [])

    for terminal in terminals:
        if terminal.get("id") == device_id:
            return terminal

    return None


def evaluate_terminal_connection(
    observation,
    settings,
    is_connected=False,
):
    """Bedöm om en betrodd terminal får anslutas eller bör kopplas från."""
    config = _terminal_settings(settings)

    if not config.get("enabled", False):
        return {
            "action": "none",
            "allowed": False,
            "reason": "Automatiska terminalanslutningar är avstängda.",
        }

    device_id = observation.get("id") or observation.get("address")
    terminal = find_terminal_config(settings, device_id)

    if not terminal:
        return {
            "action": "none",
            "allowed": False,
            "reason": "Enheten är inte registrerad som betrodd terminal.",
        }

    if not terminal.get("trusted", False):
        return {
            "action": "none",
            "allowed": False,
            "reason": "Terminalen är registrerad men inte betrodd.",
        }

    if not terminal.get("auto_connect", False):
        return {
            "action": "none",
            "allowed": False,
            "reason": "Automatisk anslutning är inte tillåten för terminalen.",
        }

    rssi = observation.get("rssi")

    if rssi is None:
        return {
            "action": "none",
            "allowed": False,
            "reason": "RSSI saknas; närheten kan inte bedömas säkert.",
        }

    connect_rssi = terminal.get(
        "connect_rssi",
        config.get("connect_rssi", DEFAULT_CONNECT_RSSI),
    )
    disconnect_rssi = terminal.get(
        "disconnect_rssi",
        config.get("disconnect_rssi", DEFAULT_DISCONNECT_RSSI),
    )

    if disconnect_rssi >= connect_rssi:
        return {
            "action": "none",
            "allowed": False,
            "reason": (
                "Ogiltig terminalkonfiguration: disconnect_rssi måste "
                "vara lägre än connect_rssi."
            ),
        }

    if is_connected:
        if rssi <= disconnect_rssi:
            return {
                "action": "disconnect",
                "allowed": True,
                "reason": (
                    f"RSSI {rssi} dBm är under frånkopplingsgränsen "
                    f"{disconnect_rssi} dBm."
                ),
            }

        return {
            "action": "keep",
            "allowed": True,
            "reason": "Terminalen är fortfarande inom tillåten närhet.",
        }

    if rssi >= connect_rssi:
        return {
            "action": "connect",
            "allowed": True,
            "reason": (
                f"RSSI {rssi} dBm når anslutningsgränsen "
                f"{connect_rssi} dBm."
            ),
        }

    return {
        "action": "none",
        "allowed": False,
        "reason": (
            f"RSSI {rssi} dBm är för svagt för anslutning "
            f"(krav {connect_rssi} dBm)."
        ),
    }
