"""No audio hardware or private network access in driver regression tests."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request

import pytest

import scripts.ventuno_usb_dialogue_hardware as hardware
import scripts.ventuno_usb_dialogue_once as controller


def test_no_consents_means_no_preflight_or_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(hardware, "build_ports",
                        lambda *_: pytest.fail("not authorized"))
    result = hardware.run_one_authorized_hardware_dialog(tmp_path)
    assert result["status"] == "not-authorized"
    assert result["physical_dialogue_attempted"] is False


def test_preflight_refuses_non_runner_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    other = tmp_path / "MyAI"
    other.mkdir()
    with pytest.raises(ValueError):
        hardware._must_be_isolated(other)


def test_preflight_allows_only_new_runner_subfolder(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    folder = tmp_path / "myai-usb-dialog-a1b2"
    folder.mkdir()
    hardware._must_be_isolated(folder)


def test_capture_invokes_one_three_second_arecord_only(monkeypatch):
    monkeypatch.setattr(hardware, "_require_executable", lambda _: "/usr/bin/arecord")
    called = []
    def run(argv, **kwargs):
        called.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"\x11" * 96000, stderr=b"")
    monkeypatch.setattr(hardware.subprocess, "run", run)
    result = hardware.capture_one_three_second_pcm()
    assert len(result) == 96000
    assert len(called) == 1
    argv, params = called[0]
    assert argv == [
        "/usr/bin/arecord", "--quiet", "--device=plughw:1,0",
        "--format=S16_LE", "--rate=16000", "--channels=1",
        "--duration=3", "--file-type=raw", "-",
    ]
    assert params["stdout"] == hardware.subprocess.PIPE
    assert params["timeout"] <= 7


@pytest.mark.parametrize("exit_code,count", [(1,0),(0,10),(0,120000)])
def test_bad_capture_fails_closed_without_leaking(monkeypatch, exit_code, count):
    monkeypatch.setattr(hardware, "_require_executable", lambda _: "/usr/bin/arecord")
    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=exit_code, stdout=b"x" * count,
        stderr=b"SECRET_USER_AUDIO_NOT_FOR_LOGS",
    ))
    with pytest.raises(ValueError) as info:
        hardware.capture_one_three_second_pcm()
    assert "SECRET" not in str(info.value)


def test_whisper_receives_pcm_on_stdin_and_no_logs(monkeypatch, tmp_path):
    data = bytes(96000)
    called = []
    def run(cmd, **kwargs):
        called.append((cmd, kwargs))
        return SimpleNamespace(returncode=0,
                               stdout=b'{"transcript":"Vad heter du?"}',
                               stderr=b"secret")
    monkeypatch.setattr(hardware.subprocess, "run", run)
    value = hardware._limited_whisper_child(
        tmp_path, tmp_path / "myai-voice-staging/bin/python",
        tmp_path / "myai-whisper-tiny-model", data,
    )
    assert value == "Vad heter du?"
    assert len(called) == 1
    cmd, args = called[0]
    assert cmd[1:3] == ["-I", "-c"]
    assert args["input"] == data
    assert args["timeout"] <= 175
    assert args["env"]["HF_HUB_OFFLINE"] == "1"
    assert args["stdout"] == hardware.subprocess.PIPE
    assert "secret" not in value


def test_unbounded_child_response_or_bad_format_never_returned(monkeypatch, tmp_path):
    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=b'x' * 2048,
        stderr=b"private transcript",
    ))
    with pytest.raises(ValueError) as info:
        hardware._limited_whisper_child(tmp_path, tmp_path / "python",
                                       tmp_path / "model", b"\x00" * 96000)
    assert "private transcript" not in str(info.value)


def test_local_geniex_receives_only_approved_question(monkeypatch):
    calls = []
    def respond(request, *, timeout):
        calls.append(request)
        if isinstance(request, str):
            return {"data": [{"id": "running-model"}]}
        assert isinstance(request, Request)
        payload = json.loads(request.data)
        assert payload["max_tokens"] == 28
        assert payload["stream"] is False
        assert payload["model"] == "running-model"
        assert "vad heter du" in payload["messages"][0]["content"]
        return {"choices":[{"message":{"content":"Jag heter MyAI."}}]}
    monkeypatch.setattr(hardware.api_bridge, "fetch_small_json", respond)
    assert hardware._local_short_response("vad heter du") == "Jag heter MyAI."
    assert len(calls) == 2


@pytest.mark.parametrize("text", [
    "radera hårddisken", "vilken tid är det", "vad heter du; shutdown",
])
def test_model_not_contacted_for_any_unapproved_transcription(monkeypatch, text):
    monkeypatch.setattr(hardware.api_bridge, "fetch_small_json",
                        lambda *a, **k: pytest.fail("must not call model"))
    with pytest.raises(ValueError):
        hardware._local_short_response(text)


def test_hardware_ports_only_construct_after_isolated_preflight(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    root = tmp_path / "myai-usb-dialog-work"
    root.mkdir()
    monkeypatch.setattr(hardware, "_preflight", lambda _: (
        root/"bin/python",root/"model",root/"espeak-ng",root/"espeak-ng-data",
    ))
    monkeypatch.setattr(hardware, "_require_executable", lambda _: "/usr/bin/aplay")
    ports = hardware.build_ports(root)
    assert isinstance(ports, controller.DialogPorts)
    assert callable(ports.capture)
    assert callable(ports.transcribe_local)
    assert callable(ports.answer_local)
    assert callable(ports.synthesize_local)
    assert callable(ports.play_usb)


def test_playback_invocation_is_a_single_capped_wav_transfer(monkeypatch, tmp_path):
    root=tmp_path/"myai-usb-dialog-test"
    root.mkdir()
    monkeypatch.setattr(hardware, "_preflight", lambda _: (
        root/"bin/python",root/"model",root/"espeak-ng",root/"espeak-ng-data",
    ))
    monkeypatch.setattr(hardware, "_require_executable", lambda _: "/usr/bin/aplay")
    p=hardware.build_ports(root)
    captures=[]
    def fake(cmd, **kwargs):
        captures.append((cmd,kwargs))
        return SimpleNamespace(returncode=0,stdout=b"",stderr=b"")
    monkeypatch.setattr(hardware.subprocess,"run",fake)
    assert p.play_usb(b"small WAV bytes") is True
    assert len(captures)==1
    cmd,options=captures[0]
    assert cmd==[
        "/usr/bin/aplay","--quiet","--device=plughw:1,0","--file-type=wav","-",
    ]
    assert options["input"]==b"small WAV bytes"
    assert options["timeout"] <= 9


def test_audible_swedish_cue_low_peak_and_only_on_speaker(
    monkeypatch, tmp_path,
):
    import array
    import io
    import wave

    root = tmp_path / "myai-usb-dialog-work"
    root.mkdir()
    monkeypatch.setattr(hardware, "_preflight", lambda _: (
        root / "bin/python", root / "model", root / "espeak-ng", root / "espeak-ng-data",
    ))
    monkeypatch.setattr(hardware, "_require_executable", lambda _: "/usr/bin/aplay")

    raw = io.BytesIO()
    with wave.open(raw, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(array.array("h", [21000] * 24000).tobytes())
    wav_source = raw.getvalue()

    calls = []
    def process(argv, **kw):
        calls.append((argv, kw))
        if argv[0].endswith("espeak-ng"):
            assert argv[-1] == "Vänta en sekund. Säg sedan: Vad heter du."
            assert "--stdout" in argv
            return SimpleNamespace(returncode=0, stdout=wav_source, stderr=b"")
        assert argv == ["/usr/bin/aplay", "--quiet", "--device=plughw:1,0",
                        "--file-type=wav", "-"]
        with wave.open(io.BytesIO(kw["input"])) as limited:
            samples = array.array("h")
            samples.frombytes(limited.readframes(limited.getnframes()))
        assert max(abs(s) for s in samples) <= int(32767 * 0.04)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(hardware.subprocess, "run", process)
    ports = hardware.build_ports(root)
    assert ports.audible_start_cue is not None
    assert ports.audible_start_cue() is True
    assert len(calls) == 2
    assert calls[0][0][0].endswith("espeak-ng")
    assert calls[1][0][0] == "/usr/bin/aplay"


def test_unusable_spoken_cue_does_not_open_speaker(monkeypatch, tmp_path):
    root = tmp_path / "myai-usb-dialog-work"
    root.mkdir()
    monkeypatch.setattr(hardware, "_preflight", lambda _: (
        root / "bin/python", root / "model", root / "espeak-ng", root / "espeak-ng-data",
    ))
    monkeypatch.setattr(hardware, "_require_executable", lambda _: "/usr/bin/aplay")
    calls = []
    def process(argv, **kwargs):
        calls.append(argv)
        assert argv[0].endswith("espeak-ng")
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"unsafe-stderr")
    monkeypatch.setattr(hardware.subprocess, "run", process)
    p = hardware.build_ports(root)
    assert p.audible_start_cue() is False
    assert len(calls) == 1


def test_explicit_ollama_reply_uses_read_only_staged_profile(
    monkeypatch, tmp_path,
):
    root = tmp_path / "myai-usb-dialog-test"
    root.mkdir()
    (root / "source/config/profiles").mkdir(parents=True)
    profile_path = root / "source/config/profiles/ventuno_q.json"
    data = {
        "llm": {"provider": "geniex", "fallback": {"enabled": False}},
        "voice": {"enabled": False, "tts_enabled": False,
                  "handsfree_enabled": False},
        "ollama": {"url": "http://127.0.0.1:11434/api/chat",
                   "model": "qwen3:0.6b"},
    }
    source = json.dumps(data,sort_keys=True)
    profile_path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(hardware, "_preflight", lambda _: (
        root/"bin/python", root/"model", root/"espeak-ng", root/"espeak-ng-data",
    ))
    monkeypatch.setattr(hardware, "_require_executable", lambda _: "/usr/bin/aplay")
    calls = []
    def alternate(question, profile, *, provider, timeout):
        calls.append((question, provider, timeout, profile))
        return "Jag heter MyAI."
    monkeypatch.setattr(hardware, "answer_one_short_voice_question", alternate)
    p=hardware.build_ports(root, response_backend="ollama")
    assert p.answer_local("vad heter du") == "Jag heter MyAI."
    assert len(calls) == 1
    assert calls[0][0] == "vad heter du"
    assert calls[0][1] == "ollama"
    assert calls[0][2] <= 90
    assert calls[0][3] == data
    assert profile_path.read_text(encoding="utf-8") == source


def test_bad_alternate_backend_never_opens_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(
        hardware, "_preflight", lambda *args: pytest.fail("no staging"),
    )
    with pytest.raises(ValueError, match="unsupported-isolated-dialogue-backend"):
        hardware.build_ports(tmp_path, response_backend="cloud")


def test_missing_staged_profile_does_not_contact_ollama(monkeypatch, tmp_path):
    root=tmp_path/"myai-usb-dialog-staging"
    root.mkdir()
    monkeypatch.setattr(hardware,"_preflight",lambda _:(
        root/"bin/python", root/"model",root/"espeak-ng",root/"data",
    ))
    monkeypatch.setattr(hardware,"_require_executable",lambda _: "/usr/bin/aplay")
    monkeypatch.setattr(hardware,"answer_one_short_voice_question",
                        lambda *a,**k: pytest.fail("No model access"))
    with pytest.raises(ValueError,match="isolated-ollama-profile-not-found"):
        hardware.build_ports(root,response_backend="ollama")


def test_no_consent_ignores_selected_ollama_backend(monkeypatch,tmp_path):
    monkeypatch.setattr(hardware,"build_ports",lambda *a,**k:
                        pytest.fail("no model or devices without consent"))
    result=hardware.run_one_authorized_hardware_dialog(
        tmp_path, consent_to_record=False, consent_to_play=True,
        response_backend="ollama",
    )
    assert result["status"] == "not-authorized"
