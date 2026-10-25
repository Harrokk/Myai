"""Fully synthetic App Lab pilot tests. Never open a hardware microphone."""
from pathlib import Path
import runpy
import sys
import types

import numpy as np
import pytest


MAIN = (Path(__file__).resolve().parents[1]
        / 'integrations/arduino_app_lab/myai_sv_asr_once/python/main.py')


def run_pilot(monkeypatch, chunks, recognized="", fail_asr=False, fail_stop=False):
    calls = []
    captured = {}

    class FakeAlsa:
        def __init__(self, **kwargs):
            assert kwargs == {'device': 'plughw:1,0', 'shared': False, 'auto_reconnect': False}
            self.chunks = list(chunks)
            self.started = False
            self.stopped = False
            captured['mic'] = self

        def start(self):
            calls.append('mic-start')
            self.started = True

        def capture(self):
            calls.append('capture')
            assert self.started
            return self.chunks.pop(0) if self.chunks else None

        def stop(self):
            calls.append('mic-stop')
            if fail_stop:
                raise RuntimeError('private device details')
            self.stopped = True

    class FakeAsr:
        def __init__(self, mic, language):
            assert language == 'sv'
            self.mic = mic

        def transcribe(self, duration):
            assert duration == 5
            calls.append('asr-start')
            while self.mic.chunks:
                self.mic.capture()
            if fail_asr:
                raise RuntimeError('PRIVATE TEXT MUST NOT LEAK')
            return recognized

    class FakeApp:
        @staticmethod
        def run(user_loop):
            for _ in range(2):
                try:
                    user_loop()
                except StopIteration:
                    pass

    def package(name):
        p = types.ModuleType(name)
        p.__path__ = []
        monkeypatch.setitem(sys.modules, name, p)
        return p

    package('arduino')
    package('arduino.app_bricks')
    asr = package('arduino.app_bricks.asr')
    asr.AutomaticSpeechRecognition = FakeAsr
    package('arduino.app_peripherals')
    micpkg = package('arduino.app_peripherals.microphone')
    micpkg.ALSAMicrophone = FakeAlsa
    app = package('arduino.app_utils')
    app.App = FakeApp
    namespace = runpy.run_path(str(MAIN))
    return captured['mic'], calls, namespace


def test_clear_pcm_and_correct_phrase(monkeypatch, capsys):
    samples = np.full(1024, 12000, dtype=np.int16)
    mic, calls, ns = run_pilot(monkeypatch, [samples, samples], 'Vad heter du?')
    out = capsys.readouterr().out
    assert mic.stopped
    assert calls == ['mic-start', 'asr-start', 'capture', 'capture', 'mic-stop']
    assert out.count('pcm-first-chunk-speak-now') == 1
    assert 'MYAI_ASR: pcm-level-present' in out
    assert 'MYAI_ASR: reference-recognized' in out
    assert 'Vad heter du?' not in out
    assert ns['mic'].sample_count == 2048


@pytest.mark.parametrize('chunks,expected', [
    ([np.zeros(1024, dtype=np.int16)], 'near-silent'),
    ([np.full(512, 35, dtype=np.int16)], 'low'),
    ([], 'no-pcm'),
    ([None, np.full(512, 9000, dtype=np.int16)], 'present'),
])
def test_signal_level_categories(monkeypatch, capsys, chunks, expected):
    _, _, _ = run_pilot(monkeypatch, chunks)
    out = capsys.readouterr().out
    assert 'MYAI_ASR: pcm-level-' + expected in out
    assert 'MYAI_ASR: no-final-text' in out


def test_unknown_nonempty_speech_never_leaked(monkeypatch, capsys):
    run_pilot(monkeypatch, [np.full(1024, 3000, dtype=np.int16)], 'Min adress är 1234')
    out = capsys.readouterr().out
    assert 'MYAI_ASR: other-nonempty-text' in out
    assert 'adress' not in out
    assert '1234' not in out


def test_failed_asr_redacted_and_released(monkeypatch, capsys):
    mic, _, _ = run_pilot(monkeypatch, [], fail_asr=True)
    out = capsys.readouterr().out
    assert mic.stopped
    assert 'MYAI_ASR: unavailable-or-failed' in out
    assert 'PRIVATE' not in out


def test_release_failure_fails_closed(monkeypatch, capsys):
    _, _, _ = run_pilot(monkeypatch, [], fail_stop=True)
    out = capsys.readouterr().out
    assert 'MYAI_ASR: microphone-release-failed' in out
    assert 'private device details' not in out


def test_no_extra_pcm_recording_or_network_io():
    text = MAIN.read_text(encoding='utf-8')
    assert 'super().capture()' in text
    assert 'asr.transcribe(duration=5)' in text
    for forbidden in ('record_pcm(', 'record_wav(', 'open(', 'requests.', 'websocket.', 'audio_chunk.tobytes(', 'print(recognized', 'print(chunk', 'write_bytes('):
        assert forbidden not in text
