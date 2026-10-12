"""ALSA listing-only inventory tests. No sound hardware accessed."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.ventuno_alsa_capture_inventory as mod


def test_proc_pcm_counts_only_capture_and_playback_ids(tmp_path):
    pcm = tmp_path / "pcm"
    pcm.write_text(
        "00-00: Private Microphone Label : capture 1\n"
        "00-01: Private Speaker Label : playback 1\n"
        "00-02: More private : playback 1 : capture 1\n",
        encoding="utf-8",
    )
    result = mod.proc_pcm_inventory(pcm)
    assert result["proc_pcm_readable"] is True
    assert result["capture_pcm_hardware_pairs"] == [[0, 0], [0, 2]]
    assert result["playback_pcm_hardware_pairs"] == [[0, 1], [0, 2]]
    assert "Private" not in str(result)


def test_missing_proc_pcm_is_inconclusive(tmp_path):
    assert mod.proc_pcm_inventory(tmp_path / "none")["proc_pcm_readable"] is False


def test_oversize_proc_pcm_fails_closed(tmp_path):
    file = tmp_path / "pcm"
    file.write_bytes(b"a" * (mod.MAX_PROC_BYTES + 1))
    result = mod.proc_pcm_inventory(file)
    assert result["proc_pcm_scan_truncated"] is True
    assert result["proc_pcm_readable"] is False


def test_arecord_l_reports_numbers_not_hardware_names():
    listing = (b"**** List of CAPTURE Hardware Devices ****\n"
               b"card 0: Private [Private], device 0: Microphone [Microphone]\n"
               b"card 1: Else [Private], device 3: ALSA Device [Secret]\n")
    r = mod.classify_arecord_list(listing, "-l")
    assert r["capture_hardware_pairs"] == [[0, 0], [1, 3]]
    assert "Private" not in str(r)


def test_arecord_L_reports_only_allowlisted_pcm_aliases():
    listing = (b"null\n  discard all samples\n"
               b"default\n  default card/private path\n"
               b"sysdefault\nplughw\nhw\n"
               b"personal-secret-sound-source\n  secret data\n")
    r = mod.classify_arecord_list(listing, "-L")
    assert r["aliases_present"] == ["default", "sysdefault", "plughw", "hw"]
    assert "personal-secret" not in str(r)


def test_unsafe_argument_refused():
    with pytest.raises(ValueError, match="only-read-only"):
        mod.classify_arecord_list(b"", "-D hw:0,0")


def test_only_list_commands_and_no_microphone_stream(monkeypatch, tmp_path):
    pcm = tmp_path / "pcm"
    pcm.write_text("00-00: name : capture 1")
    invocations = []
    def fake(argv, **kwargs):
        invocations.append(argv)
        assert argv in (["/usr/bin/arecord", "-l"],
                        ["/usr/bin/arecord", "-L"])
        assert kwargs["timeout"] <= 5
        if argv[-1] == "-l":
            return SimpleNamespace(returncode=0,
                stdout=b"card 0: X [X], device 0: Y [Y]", stderr=b"")
        return SimpleNamespace(returncode=0,
            stdout=b"default\nhw\nplughw\n", stderr=b"")
    monkeypatch.setattr(mod.subprocess, "run", fake)
    r = mod.list_alsa_capture(tool="/usr/bin/arecord", proc_pcm=pcm)
    assert len(invocations) == 2
    assert r["alsa_default_alias_listed"] is True
    assert r["alsa_capture_hardware_pairs"] == [[0, 0]]
    assert r["audio_stream_opened"] is False
    assert r["microphone_recorded"] is False
    assert r["services_changed"] is False
    assert r["production_config_modified"] is False
    assert r["status"] == "alsa-listing-observed-capture-routing-unverified"


def test_failed_listing_remains_inconclusive(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.subprocess, "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout=b"", stderr=b"private path"
        ))
    r = mod.list_alsa_capture(tool="/usr/bin/arecord",
                               proc_pcm=tmp_path / "none")
    assert r["status"] == "inconclusive-alsa-route"
    assert "private path" not in str(r)


def test_no_tool_does_not_call_subprocess(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k:
                        pytest.fail("no arecord binary"))
    r = mod.list_alsa_capture(proc_pcm=tmp_path / "pcm")
    assert r["status"] == "arecord-not-installed"


def test_symlink_proc_pcm_is_rejected(tmp_path):
    original = tmp_path / "original"
    original.write_text("00-00: private : capture 1")
    symlink = tmp_path / "pcm"
    try:
        symlink.symlink_to(original)
    except OSError:
        pytest.skip("symlink unsupported")
    assert mod.proc_pcm_inventory(symlink)["proc_pcm_readable"] is False
