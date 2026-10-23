"""No real mic or speaker: synthetic tests for the actual Swedish cue WAV policy."""
import array
import io
import os
from pathlib import Path
import wave
from types import SimpleNamespace

import pytest

from scripts import ventuno_smoke_cue_render_preflight as pre
from scripts.ventuno_usb_dialogue_hardware import SPOKEN_START_CUE
from scripts.ventuno_usb_speaker_smoke import MAX_DURATION_SECONDS


def dummy_wav(seconds):
    b=io.BytesIO()
    with wave.open(b,"wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(array.array("h",[19000]*int(16000*seconds)).tobytes())
    return b.getvalue()


def setup(monkeypatch,tmp_path,voice=b""):
    monkeypatch.setenv("RUNNER_TEMP",str(tmp_path))
    monkeypatch.setattr(pre.platform,"machine",lambda:"aarch64")
    root=tmp_path/"myai-cue-render-verified"
    root.mkdir()
    stage=root/"myai-tts-espeak-stage"
    stage.mkdir()
    fake_exe=stage/"synthetic-espeak"
    fake_exe.write_bytes(b"synthetic binary not executed")
    voicedata=stage/"synthetic-voices"
    voicedata.mkdir()
    monkeypatch.setattr(pre,"espeak_paths",lambda path:(fake_exe,voicedata))
    calls=[]
    def fake(cmd,**kwargs):
        calls.append((cmd,kwargs))
        return SimpleNamespace(returncode=0, stdout=voice, stderr=b"")
    monkeypatch.setattr(pre.subprocess,"run",fake)
    return root,calls


def test_no_explicit_synthetic_permission_means_zero_operations(monkeypatch,tmp_path):
    monkeypatch.setattr(pre,"espeak_paths",lambda *_:pytest.fail("must not inspect"))
    report=pre.evaluate_cue_render(root=tmp_path)
    assert report["status"]=="not-authorized"
    assert report["physical_microphone_opened"] is False
    assert report["physical_speaker_opened"] is False
    assert report["authorizes_physical_recording"] is False
    assert report["authorizes_physical_playback"] is False


def test_fixed_literal_matches_driver_and_safe_under_policy(monkeypatch,tmp_path):
    root,calls=setup(monkeypatch,tmp_path,dummy_wav(2.85))
    report=pre.evaluate_cue_render(root=root,synthetic_only=True)
    assert report["status"]==pre.STATUS
    assert report["exact_live_cue_used"]
    assert report["audio_duration_seconds"]==2.85
    assert report["audio_duration_seconds"] < MAX_DURATION_SECONDS
    assert report["digital_peak_cap"]==0.04
    assert not report["physical_microphone_opened"]
    assert not report["physical_speaker_opened"]
    assert not report["production_modified"]
    assert not report["generated_wav_saved"]
    assert len(calls)==1
    args, opts=calls[0]
    assert args[-1]==SPOKEN_START_CUE
    assert args[-4:-1]==["-v","sv","--stdout"]
    assert not any("aplay" in str(x) or "arecord" in str(x) for x in args)
    assert opts["timeout"]<=9
    assert opts["stderr"]==pre.subprocess.PIPE


def test_long_swedish_cue_fails_closed_instead_of_opening_speaker(
    monkeypatch,tmp_path,
):
    root,_=setup(monkeypatch,tmp_path,dummy_wav(3.8))
    result=pre.evaluate_cue_render(root=root,synthetic_only=True)
    assert result["status"]=="reject-cue-exceeds-quiet-wav-policy"
    assert result["authorizes_physical_playback"] is False


@pytest.mark.parametrize("status,wire,expected",[
    (1,dummy_wav(2.0),"reject-cue-render-size-or-process"),
    (0,b"","reject-cue-render-size-or-process"),
    (0,b"x"*800_000,"reject-cue-render-size-or-process"),
    (0,b"x"*100,"reject-cue-exceeds-quiet-wav-policy"),
])
def test_failed_or_corrupt_synthetic_render_never_authorizes_physical_audio(
    monkeypatch,tmp_path,status,wire,expected,
):
    root,calls=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(pre.subprocess,"run",
        lambda *a,**k:SimpleNamespace(returncode=status,stdout=wire,stderr=b"secret"))
    result=pre.evaluate_cue_render(root=root,synthetic_only=True)
    assert result["status"]==expected
    assert not result["authorizes_physical_playback"]
    assert not result["user_audio_used"]


def test_invalid_root_or_machine_cannot_execute_render(monkeypatch,tmp_path):
    root,calls=setup(monkeypatch,tmp_path,dummy_wav(1.5))
    monkeypatch.setattr(pre.platform,"machine",lambda:"x86_64")
    result=pre.evaluate_cue_render(root=root,synthetic_only=True)
    assert result["status"]=="reject-non-arm64"
    monkeypatch.setattr(pre.platform,"machine",lambda:"aarch64")
    old_root=tmp_path/"production"
    old_root.mkdir()
    result=pre.evaluate_cue_render(root=old_root,synthetic_only=True)
    assert result["status"]=="reject-unsafe-root"
    assert calls==[]


def test_cue_cannot_be_confused_with_authorized_user_speech():
    from scripts.ventuno_usb_dialogue_once import (
        approved_short_question, classify_unapproved_question,
    )
    assert "Vänta en sekund" in SPOKEN_START_CUE
    assert "Säg:" in SPOKEN_START_CUE
    assert approved_short_question(SPOKEN_START_CUE) is None
    assert classify_unapproved_question(SPOKEN_START_CUE)==(
        "spoken-cue-echo-suspected"
    )


def test_preflight_module_has_no_device_and_no_production_signing():
    src=Path(pre.__file__).read_text()
    for bad in ("arecord", "aplay", "SelfDevPromotionManager",
                "systemctl start", "sudo", "os.chmod(", "open('/dev"):
        assert bad not in src
    assert '"authorizes_physical_recording": False' in src
    assert '"authorizes_physical_playback": False' in src
