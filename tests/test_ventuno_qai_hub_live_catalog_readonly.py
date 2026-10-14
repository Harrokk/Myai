"""No real QAI Hub client/network in tests: all clients are synthetic."""
from types import SimpleNamespace

from scripts import ventuno_qai_hub_live_catalog_readonly as api


def f(version="2.46", full="2.46.0.260800", name="QAIRT"):
    return SimpleNamespace(name=name, api_version=version, full_version=full)


def device(name="Arduino VENTUNO Q"):
    return SimpleNamespace(name=name)


class Client:
    def __init__(self, frameworks=None, devices=None, fail=False, log=False):
        self.frameworks = [f()] if frameworks is None else frameworks
        self.devices = [device()] if devices is None else devices
        self.calls = []
        self.fail = fail
        self.log = log

    def get_frameworks(self):
        self.calls.append(("get_frameworks",))
        if self.log:
            print("SECRET_FRAMEWORK_API_RESPONSE")
        if self.fail:
            raise RuntimeError("SECRET_TOKEN_FROM_API_ERROR")
        return self.frameworks

    def get_devices(self, *, name):
        self.calls.append(("get_devices", name))
        return self.devices

    def submit_compile_job(self, *args, **kwargs):
        raise AssertionError("No compile job allowed")

    def upload_model(self, *args, **kwargs):
        raise AssertionError("No model upload allowed")


def test_no_consent_must_not_instantiate_client():
    result = api.run_readonly_query(
        confirm=False, machine="x86_64",
        client_factory=lambda: (_ for _ in ()).throw(
            AssertionError("Client was unexpectedly instantiated")
        ),
    )
    assert result["status"] == "no_go_readonly_api_not_authorized"
    assert result["query_attempted"] is False


def test_wrong_machine_no_client_or_network():
    result = api.run_readonly_query(
        confirm=True, machine="aarch64",
        client_factory=lambda: (_ for _ in ()).throw(
            AssertionError("Do not access vendor API on VENTUNO")
        ),
    )
    assert result["status"] == "no_go_host_must_be_x86"


def test_only_two_allowlisted_read_calls_with_explicit_consent():
    client = Client()
    result = api.run_readonly_query(
        confirm=True, machine="x86_64", client_factory=lambda: client)
    assert client.calls == [
        ("get_frameworks",), ("get_devices", "Arduino VENTUNO Q")
    ]
    assert result["status"] == "read_only_catalog_and_target_listed_htp_unverified"
    assert result["query_completed"] is True
    assert result["live_qairt_246_catalog_reported"] is True
    assert result["exact_target_qairt_246_compile_link_eligibility_verified"] is False
    assert result["htp_operator_support_verified"] is False
    assert result["model_or_context_uploaded"] is False
    assert result["cloud_job_submitted"] is False
    assert result["qnn_or_npu_executed"] is False


def test_no_qairt_246_in_mock_catalog_is_no_go():
    result = api.run_readonly_query(
        confirm=True, machine="x86_64",
        client_factory=lambda: Client(frameworks=[f("2.45", "2.45.0"),
                                                   f("2.50", "2.50.0")]),
    )
    assert result["status"] == "no_go_qairt_246_not_in_returned_catalog"
    assert result["live_qairt_246_catalog_reported"] is False


def test_proxy_device_never_accepted():
    result = api.run_readonly_query(
        confirm=True, machine="x86_64",
        client_factory=lambda: Client(devices=[device("QCS8275 (Proxy)")]),
    )
    assert result["status"] == "no_go_exact_arduino_ventuno_q_not_listed"
    assert result["exact_arduino_ventuno_q_in_device_list"] is False


def test_bad_246_full_version_fails_closed():
    result = api.run_readonly_query(
        confirm=True, machine="x86_64",
        client_factory=lambda: Client(frameworks=[f(full="2.50.0.260828")]),
    )
    assert result["status"] == "no_go_qairt_246_version_metadata_inconsistent"
    assert result["live_qairt_246_catalog_reported"] is False


def test_duplicate_246_framework_records_cannot_masquerade_as_catalog():
    result = api.run_readonly_query(
        confirm=True, machine="x86_64",
        client_factory=lambda: Client(frameworks=[f(), f()]),
    )
    assert result["status"] == "no_go_untrusted_or_ambiguous_service_response"
    assert result["query_completed"] is False


def test_unrecognized_framework_shape_and_too_many_entries():
    assert api.classify_frameworks("QAIRT") == ("invalid_catalog", None, None)
    assert api.classify_frameworks([f()] * (api.MAX_FRAMEWORKS + 1)) == (
        "invalid_catalog", None, None
    )
    assert api.classify_frameworks([object()]) == (
        "invalid_catalog", None, None
    )


def test_client_error_and_printed_secret_suppressed(capsys):
    result = api.run_readonly_query(
        confirm=True, machine="x86_64",
        client_factory=lambda: Client(fail=True, log=True),
    )
    logs = capsys.readouterr()
    assert logs.out == logs.err == ""
    assert "SECRET" not in str(result)
    assert result["status"] == "no_go_readonly_api_query_failed"
    assert result["raw_responses_errors_or_credentials_exported"] is False


def test_get_devices_failure_does_not_expose_account_error(capsys):
    class BrokenDevices(Client):
        def get_devices(self, **kwargs):
            print("SECRET_ACCOUNT_ID")
            raise RuntimeError("SECRET_ACCOUNT_TOKEN")
    result = api.run_readonly_query(
        confirm=True, machine="x86_64",
        client_factory=BrokenDevices,
    )
    assert "SECRET" not in str(result)
    assert "SECRET" not in capsys.readouterr().out
    assert result["query_completed"] is False


def test_device_list_untrusted_shape_is_unknown():
    result = api.run_readonly_query(
        confirm=True, machine="x86_64",
        client_factory=lambda: Client(devices=["Arduino VENTUNO Q"]),
    )
    assert result["status"] == "no_go_untrusted_or_ambiguous_service_response"
    assert result["exact_arduino_ventuno_q_in_device_list"] is None


def test_reports_do_not_include_other_catalog_devices_or_versions():
    client = Client(frameworks=[f(), f("2.50", "2.50.0")],
                    devices=[device(), device("Private Device Name")])
    result = api.run_readonly_query(
        confirm=True, machine="x86_64", client_factory=lambda: client
    )
    assert "Private Device Name" not in str(result)
    assert "2.50.0" not in str(result)
    assert result["raw_responses_errors_or_credentials_exported"] is False
