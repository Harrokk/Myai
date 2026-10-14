"""Mock-only safety controls for public human Swedish Whisper Tiny STT."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import scripts.ventuno_natural_swedish_stt as m


def prepared(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNNER_TEMP",str(tmp_path))
    root=tmp_path/"myai-natural-sv-pytest"
    root.mkdir()
    tiny=root/m.SMALL_FOLDER
    tiny.mkdir()
    py=root/m.STT_PYTHON
    py.parent.mkdir(parents=True,exist_ok=True)
    py.write_text("test-only")
    monkeypatch.setattr(m,"model_integrity",lambda _:{"model_sha256":m.EXPECTED_MODEL_SHA256})
    monkeypatch.setattr(m,"mem_available_kib",lambda:12*1024*1024)
    monkeypatch.setattr(m,"disk_free_bytes",lambda _:10*1024**3)
    monkeypatch.setattr(m,"_fetch_human_audio",lambda:b"OggSpinned_public_only")
    return root


def worker_payload(correct=True):
    rows=[]
    for variant in ("original","three-second-capture"):
        for beam in (1,5):
            rows.append({
                "variant":variant,"beam":beam,"matched":correct,
                "distance_band":"0" if correct else "6-10",
                "target_words_present":3 if correct else 1,
                "target_words_in_order":correct,
                "seconds":0.15,
            })
    return {
        "model_loaded":True,"microphone_opened":False,
        "speaker_opened":False,"user_audio_processed":False,
        "transcript_persisted":False,"cases":rows,"peak_rss_mib":250.,
    }


def test_defaults_off_and_no_download(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_fetch_human_audio",lambda:pytest.fail("must not download"))
    got=m.compare_human_swedish(root,machine="aarch64")
    assert got["status"]=="not-authorized"
    assert got["microphone_opened"] is False
    assert got["production_changed"] is False


def test_wrong_architecture_rejects_before_fetch(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_fetch_human_audio",lambda:pytest.fail("no download"))
    assert m.compare_human_swedish(
        root,authorized=True,machine="x86_64"
    )["status"]=="blocked-architecture"


def test_wrong_workspace_rejected(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    invalid=tmp_path/"not-natural-work"
    invalid.mkdir()
    got=m.compare_human_swedish(invalid,authorized=True,machine="aarch64")
    assert got["status"]=="blocked-nonisolated-workspace"


def test_memory_resource_gate(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"mem_available_kib",lambda:0)
    got=m.compare_human_swedish(root,authorized=True,machine="aarch64")
    assert got["status"]=="blocked-resource-gate"


def test_bad_tiny_weights_rejected(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"model_integrity",lambda _:{"model_sha256":"bad"})
    got=m.compare_human_swedish(root,authorized=True,machine="aarch64")
    assert got["status"]=="blocked-unverified-whisper-tiny"


def test_download_mismatch_blocks_worker(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_fetch_human_audio",lambda:None)
    monkeypatch.setattr(m,"_limited_child",lambda *a,**kw:pytest.fail("not allowed"))
    got=m.compare_human_swedish(root,authorized=True,machine="aarch64")
    assert got["status"]=="public-human-audio-download-or-hash-failed"


def test_successful_human_samples_emit_metrics_but_never_transcript(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    called=[]
    def simulate(py,source,workspace,*,model=None,pcm=None):
        assert model.name==m.SMALL_FOLDER
        assert pcm==b"OggSpinned_public_only"
        assert workspace==root
        assert "hur mår du" in source
        called.append(1)
        return {"ok":True,"payload":worker_payload(correct=False)}
    monkeypatch.setattr(m,"_limited_child",simulate)
    got=m.compare_human_swedish(root,authorized=True,machine="aarch64")
    assert got["status"]=="licensed-human-swedish-tiny-comparison-complete"
    assert len(called)==1
    assert got["fixture_sha256_verified"] is True
    assert len(got["tiny_results"])==4
    assert not any(x["matched"] for x in got["tiny_results"])
    assert got["tiny_peak_rss_mib"]==250.
    exported=json.dumps(got)
    assert "decoded" not in exported
    assert "transcription" not in exported
    assert got["speech_saved"] is False
    assert got["geniex_called"] is False
    assert got["ollama_called"] is False


def test_worker_injects_raw_transcript_rejected(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    unsafe=worker_payload()
    unsafe["cases"][0]["transcript"]="this must not leak"
    monkeypatch.setattr(m,"_limited_child",lambda *a,**kw:{"ok":True,"payload":unsafe})
    got=m.compare_human_swedish(root,authorized=True,machine="aarch64")
    assert got["status"]=="invalid-worker-case"
    assert "this must not leak" not in json.dumps(got)


def test_worker_rejects_spurious_microphone_use(monkeypatch,tmp_path):
    root=prepared(monkeypatch,tmp_path)
    unsafe=worker_payload()
    unsafe["microphone_opened"]=True
    monkeypatch.setattr(m,"_limited_child",lambda *a,**kw:{"ok":True,"payload":unsafe})
    got=m.compare_human_swedish(root,authorized=True,machine="aarch64")
    assert got["status"]=="invalid-worker-envelope"


def test_public_audio_verified_exact_bytes_and_sha(monkeypatch):
    raw=b"OggS"+b"\0"*(m.EXPECTED_BYTES-4)
    assert not m.validate_public_recording(raw)
    monkeypatch.setattr(m,"EXPECTED_SHA256",hashlib.sha256(raw).hexdigest())
    assert m.validate_public_recording(raw)
    assert not m.validate_public_recording(raw+b"\0")
    assert not m.validate_public_recording(b"WRONG"+raw[5:])


def test_http_redirect_fails_closed(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):return None
        def geturl(self):return "https://untrusted.invalid/audio.ogg"
        def read(self,*a):return b"OggS"
    monkeypatch.setattr(m,"urlopen",lambda *a,**kw:Response())
    assert m._fetch_human_audio() is None


def test_fixture_source_is_immutable_licensed_and_small():
    assert m.SOURCE.startswith("https://upload.wikimedia.org/wikipedia/commons/archive/")
    assert "20071106020716" in m.SOURCE
    assert m.EXPECTED_BYTES==15152
    assert len(m.EXPECTED_SHA256)==64
    assert m.TARGET=="hur mår du"
    assert "CC BY 2.0 France" in m.__doc__
    assert "Vad heter du" not in m._HUMAN_WORKER
    assert "arecord" not in m._HUMAN_WORKER
    assert "aplay" not in m._HUMAN_WORKER
    assert "initial_prompt" not in m._HUMAN_WORKER
