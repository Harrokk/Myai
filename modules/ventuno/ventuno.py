from core.config import load_settings
from core.ventuno_rpc import VentunoRPCClient


def ventuno_rpc_status():
    settings = load_settings()
    client = VentunoRPCClient(
        settings
    )
    status = client.status()

    return (
        "VENTUNO RPC: "
        f"enabled={status['enabled']}, "
        f"connected={status['connected']}, "
        f"write_enabled={status['write_enabled']}, "
        f"read_methods={len(status['allowed_read_methods'])}, "
        f"write_methods={len(status['allowed_write_methods'])}"
    )


def read_ventuno_mcu_status(
    settings=None,
    client=None,
):
    settings = settings or load_settings()
    active_client = (
        client
        or VentunoRPCClient(
            settings
        )
    )

    if not active_client.enabled:
        return (
            "VENTUNO STM32 RPC är avstängt. "
            "Ingen MCU-anslutning gjordes."
        )

    try:
        ping = active_client.call(
            "myai_ping"
        )
        uptime = active_client.call(
            "myai_uptime_ms"
        )
        status = active_client.call(
            "myai_mcu_status"
        )

        return (
            "VENTUNO STM32:\n"
            f"Ping: {ping}\n"
            f"Uptime: {uptime} ms\n"
            f"Status: {status}"
        )
    finally:
        active_client.disconnect()


def ventuno_mcu_status():
    try:
        return read_ventuno_mcu_status()
    except Exception as error:
        return (
            "VENTUNO STM32-status kunde "
            f"inte läsas: {error}"
        )


TOOLS = {
    "ventuno_rpc_status": {
        "function": ventuno_rpc_status,
        "description": (
            "Visar konfigurationsstatus för VENTUNO Q "
            "STM32/Arduino Router RPC utan att ansluta."
        ),
    },
    "ventuno_mcu_status": {
        "function": ventuno_mcu_status,
        "description": (
            "Läser endast de tre uttryckligt allowlistade "
            "read-only diagnostikmetoderna från VENTUNO Q STM32."
        ),
    },
}
