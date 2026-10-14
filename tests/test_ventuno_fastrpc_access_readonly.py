"""Read-only FastRPC metadata report cannot leak device names or open nodes."""
from scripts import ventuno_fastrpc_access_readonly as probe


def test_routing_secure_and_nonsecure_is_exact():
    assert probe.rpc_category("fastrpc-cdsp-secure") == "cdsp_secure"
    assert probe.rpc_category("fastrpc-cdsp") == "cdsp_nonsecure"
    assert probe.rpc_category("fastrpc-cdsp-nonsecure") == "cdsp_nonsecure"
    assert probe.rpc_category("fastrpc-adsp") == "other_rpc_nodes"
    assert probe.rpc_category("ttyUSB0") is None


def test_absent_rpc_nodes_result_is_fail_closed(tmp_path):
    result = probe.classify_rpc_nodes(tmp_path)
    assert result["cdsp_secure"]["exists"] is False
    assert result["cdsp_secure"]["effective_write"] is False
    assert result["other_rpc_nodes"]["count"] == 0


def test_emitted_schema_excludes_user_identity_and_device_path(monkeypatch):
    monkeypatch.setattr(probe, "classify_rpc_nodes", lambda: {
        "cdsp_secure": {
            "exists": True, "character_device": True,
            "effective_read": False, "effective_write": False},
        "cdsp_nonsecure": {
            "exists": True, "character_device": True,
            "effective_read": True, "effective_write": True},
        "other_rpc_nodes": {"count": 3},
    })
    monkeypatch.setattr(probe, "runtime_security_indicators", lambda: {})
    result = probe.report()
    assert result["secure_cdsp_metadata_access_suggests_possible_permission_block"] is True
    assert result["device_open_attempted"] is False
    assert result["inference_attempted"] is False
    assert result["secure_cdsp_open_ability_verified"] is False
    assert not any(term in str(result).lower() for term in (
        "user_id", "password", "/dev/", "serial_number", "ip_address"))
