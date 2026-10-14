"""Safety checks for real-board read-only probe output and parsing."""
from scripts import ventuno_readonly_probe as diag


def test_report_contains_only_allowlisted_hardware_fields(monkeypatch):
    for name in (
        "clocks","temperature","memory","disk","usb_audio","connectivity",
        "accelerators","units","pcm_capabilities","qualcomm_runtime_indicators",
    ):
        monkeypatch.setattr(diag,name,lambda:{})
    monkeypatch.setattr(diag,"usb_audio_interfaces",lambda:0)
    report=diag.report()
    assert set(report)=={
        "probe","platform","cpu_frequencies","thermal","memory","root_disk",
        "usb_audio","network","accelerator_indicators_only","services",
        "privacy","audio_interface_class_count","pcm_capabilities",
        "qualcomm_runtime_indicators_only",
    }
    assert report["privacy"]=={
        "audio_recorded":False,"device_identifiers_exported":False,
        "network_addresses_exported":False,"services_modified":False
    }


def test_safe_numeric_reader_rejects_bad_contents(tmp_path):
    file=tmp_path/"value"
    assert diag.number(file) is None
    file.write_text("not-a-number",encoding="ascii")
    assert diag.number(file) is None
    file.write_text("38000",encoding="ascii")
    assert diag.number(file)==38000


def test_pcm_parsing_uses_counts_not_hardware_names(monkeypatch):
    monkeypatch.setattr(diag,"text_file",lambda *args,**kw:
        "00-00: Vendor Name : playback 1 : capture 2\n"
        "01-01: Other Name : playback 3\n")
    result=diag.pcm_capabilities()
    assert result["alsa_capture_pcm_count"]==2
    assert result["alsa_playback_pcm_count"]==4


def test_missing_systemctl_never_leaks_status_output(monkeypatch):
    def no_systemctl(*args,**kwargs):
        raise FileNotFoundError("not available")
    monkeypatch.setattr(diag.subprocess,"run",no_systemctl)
    assert diag.units()=={
        "myai":"not_listed","geniex":"not_listed","github_runner":"not_listed"
    }
