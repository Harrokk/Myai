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


TOOLS = {
    "ventuno_rpc_status": {
        "function": ventuno_rpc_status,
        "description": (
            "Visar konfigurationsstatus för VENTUNO Q "
            "STM32/Arduino Router RPC utan att ansluta."
        ),
    },
}
