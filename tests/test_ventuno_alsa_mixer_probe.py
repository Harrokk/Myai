"""No-recording regression tests for the VENTUNO ALSA mixer inventory."""
from types import SimpleNamespace

import pytest

import scripts.ventuno_alsa_mixer_probe as mod


MIXER = b"""Simple mixer control 'Speaker-private-label',0
  Capabilities: pvolume pswitch
  Playback channels: Front Left - Front Right
  Front Left: Playback 100 [100%] [on]
Simple mixer control 'Microphone-private-label',0
  Capabilities: cvolume cswitch
  Capture channels: Front Left - Front Right
  Front Left: Capture 0 [0%] [off]
  Front Right: Capture 10 [50%] [on]
"""


def test_parse_only_capture_controls_and_summarize_levels():
    result = mod.parse_capture_controls(MIXER)
    assert result == {
        "capture_controls": 1,
        "capture_switch_on_reports": 1,
        "capture_switch_off_reports": 1,
        "capture_volume_zero_reports": 1,
        "capture_volume_nonzero_reports": 1,
    }
    assert "Microphone-private-label" not in str(result)
    assert "Speaker-private-label" not in str(result)


def test_only_read_only_amixer_is_invoked(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/amixer")
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        assert argv == ["/usr/bin/amixer", "-c", "0", "scontents"]
        assert kw["timeout"] <= 5
        assert kw["check"] is False
        return SimpleNamespace(returncode=0, stdout=MIXER, stderr=b"")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    result = mod.inspect_mixer()
    assert len(calls) == 1
    assert result["status"] == "some-capture-switches-report-off"
    assert result["recording_performed"] is False
    assert result["playback_performed"] is False
    assert result["mixer_controls_changed"] is False
    assert result["production_services_changed"] is False
    assert result["physical_microphone_verified"] is False
    assert "private-label" not in str(result)


def test_missing_amixer_never_runs_command(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        mod.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("must not execute subprocess"),
    )
    assert mod.inspect_mixer()["status"] == "amixer-unavailable"


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(returncode=1, stdout=b"", stderr=b"private-text"),
        SimpleNamespace(returncode=0, stdout=b"x" * (mod.MAX_RESPONSE_BYTES + 1),
                        stderr=b""),
    ],
)
def test_failure_or_oversize_output_never_leaks_text(monkeypatch, result):
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/amixer")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw: result)
    report = mod.inspect_mixer()
    assert report["mixer_query_completed"] is False
    assert "private-text" not in str(report)
    assert "stdout" not in report and "stderr" not in report


@pytest.mark.parametrize("error", [OSError("private-text"),
                                    mod.subprocess.TimeoutExpired("amixer", 5)])
def test_os_failure_does_not_expose_error(monkeypatch, error):
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/amixer")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(mod.subprocess, "run", fail)
    report = mod.inspect_mixer()
    assert report["status"] == "mixer-query-failed"
    assert "private-text" not in str(report)


def test_readable_mixer_does_not_prove_microphone(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/amixer")
    monkeypatch.setattr(
        mod.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout=b"Simple mixer control 'Capture',0\n"
                   b"  Capabilities: cvolume cswitch\n"
                   b"  Mono: Capture 65 [65%] [on]\n",
            stderr=b"",
        ),
    )
    report = mod.inspect_mixer()
    assert report["status"] == "capture-control-metadata-readable"
    assert report["physical_microphone_verified"] is False


def test_capture_control_without_readings_is_inconclusive(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/amixer")
    monkeypatch.setattr(
        mod.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout=(
                b"Simple mixer control 'Capture',0\\n"
                b"  Capabilities: cvolume cswitch\\n"
                b"  Capture channels: Mono\\n"
                b"  Limits: Capture 0 - 63\\n"
            ).replace(b"\\n", b"\n"),
            stderr=b"",
        ),
    )
    result = mod.inspect_mixer()
    assert result["capture_controls"] == 1
    assert result["status"] == "capture-controls-without-level-readings"
    assert result["physical_microphone_verified"] is False


def test_capture_format_diagnostics_reports_only_shape_counts():
    summary = mod.capture_format_diagnostics(MIXER)
    assert summary == {
        "capture_blocks_with_percent_token": 1,
        "capture_blocks_with_switch_token": 1,
        "capture_blocks_with_channel_row": 1,
        "capture_blocks_with_enumerated_item": 0,
        "capture_blocks_with_capture_value_row": 1,
    }
    assert all(type(value) is int for value in summary.values())
    assert "private-label" not in str(summary)


def test_capture_format_diagnostics_detects_alternate_alsa_rows():
    body = (
        b"Simple mixer control 'private-control',0\n"
        b"  Capabilities: cswitch\n"
        b"  Capture channels: Mono\n"
        b"  Item0: 'private-input-label'\n"
    )
    summary = mod.capture_format_diagnostics(body)
    assert summary["capture_blocks_with_enumerated_item"] == 1
    assert summary["capture_blocks_with_percent_token"] == 0
    assert summary["capture_blocks_with_capture_value_row"] == 0
    assert "private-input-label" not in str(summary)


def test_capture_format_diagnostics_rejects_oversize():
    with pytest.raises(ValueError):
        mod.capture_format_diagnostics(b"x" * (mod.MAX_RESPONSE_BYTES + 1))


def test_capture_channel_levels_without_capture_word_are_counted():
    raw = (
        b"Simple mixer control 'private-input-control',0\n"
        b"  Capabilities: cvolume cswitch\n"
        b"  Capture channels: Front Left - Front Right\n"
        b"  Front Left: 0 [0%] [off]\n"
        b"  Front Right: 44 [73%] [on]\n"
    )
    report = mod.parse_capture_controls(raw)
    assert report == {
        "capture_controls": 1,
        "capture_switch_on_reports": 1,
        "capture_switch_off_reports": 1,
        "capture_volume_zero_reports": 1,
        "capture_volume_nonzero_reports": 1,
    }
    assert "private-input-control" not in str(report)


def test_mixed_playback_row_is_not_counted_as_capture_volume():
    raw = (
        b"Simple mixer control 'private-mixed-control',0\n"
        b"  Capabilities: pvolume cvolume pswitch cswitch\n"
        b"  Playback channels: Mono\n"
        b"  Capture channels: Mono\n"
        b"  Mono: Playback 0 [0%] [off]\n"
        b"  Mono: Capture 25 [25%] [on]\n"
    )
    report = mod.parse_capture_controls(raw)
    assert report["capture_controls"] == 1
    assert report["capture_volume_zero_reports"] == 0
    assert report["capture_volume_nonzero_reports"] == 1
    assert report["capture_switch_on_reports"] == 1
    assert report["capture_switch_off_reports"] == 0
