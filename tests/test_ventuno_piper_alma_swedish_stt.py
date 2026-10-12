"""Privacy-sanitized Piper Alma -> Whisper Tiny/Base on ARM64, mock-only."""
import array
import io
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

import scripts.ventuno_piper_alma_swedish_stt as m


def synthetic_voice():
    buf=io.BytesIO()
    with wave.open(buf,"wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(array.array("h",[5000]*22050).tobytes())
    return buf.getvalue()


def setup(monkeypatch,tmp_path):
    monkeypatch.setenv("RUNNER_TEMP",str(tmp_path))
    root=tmp_path/"myai-alma-compare-unit"
    root.mkdir()
    tiny=root/m.SMALL_FOLDER
    tiny.mkdir()
    path=root/m.STT_PYTHON
    path.parent.mkdir(parents=True)
    path.write_text("fake")
    monkeypatch.setattr(m,"mem_available_kib",lambda:12*1024*1024)
    monkeypatch.setattr(m,"disk_free_bytes",lambda _:15*1024**3)
    monkeypatch.setattr(m,"model_integrity",lambda _:{
        "model_sha256":m.EXPECTED_MODEL_SHA256
    })
    monkeypatch.setattr(m,"base_integrity",lambda _:True)
    monkeypatch.setattr(m,"_download_verified_voice",lambda _:True)
    monkeypatch.setattr(m,"_render_once",lambda *a:synthetic_voice())
    return root


def rows(match=False):
    return [{
        "beam":beam,
        "matched":match,
        "category":"approved" if match else "other-unmatched",
        "seconds":1.5,
        "proximity":{
            "distance_band":"0" if match else "6-10",
            "word_count_band":"3",
            "target_words_present":3 if match else 1,
            "target_words_aligned":3 if match else 0,
            "target_words_in_order":match,
            "exact_phrase_contained":match,
        },
    } for _ in range(2) for beam in (1,5)]


def test_unapproved_never_runs_voice(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_render_once",lambda *a:pytest.fail("no consent"))
    r=m.compare_alma_swedish(root,machine="aarch64")
    assert r["status"]=="not-authorized"
    assert r["real_microphone_opened"] is False
    assert r["speaker_opened"] is False


def test_wrong_arch_or_workspace_stops_before_download(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_download_verified_voice",lambda _:
                        pytest.fail("never download"))
    assert m.compare_alma_swedish(
        root,authorized=True,machine="x86_64"
    )["status"]=="blocked-architecture"
    wrong=tmp_path/"not-isolated"
    wrong.mkdir()
    assert m.compare_alma_swedish(
        wrong,authorized=True,machine="aarch64"
    )["status"]=="blocked-nonisolated-root"


def test_ram_gate_blocks_render(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"mem_available_kib",lambda:0)
    monkeypatch.setattr(m,"_render_once",lambda *a:pytest.fail("low RAM"))
    assert m.compare_alma_swedish(
        root,authorized=True,machine="aarch64"
    )["status"]=="blocked-resource-gate"


def test_pinned_model_hash_failure_prevents_inference(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_download_verified_voice",lambda _:False)
    monkeypatch.setattr(m,"_render_once",lambda *a:pytest.fail("no render"))
    assert m.compare_alma_swedish(
        root,authorized=True,machine="aarch64"
    )["status"]=="pinned-alma-download-or-integrity-failed"


def test_two_alma_variants_and_both_whisper_models(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    variants=[]
    monkeypatch.setattr(m,"_render_once",lambda _root,model,scale:
                        variants.append(scale) or synthetic_voice())
    inference=[]
    def worker(interpreter,source,work,*,model=None,pcm=None):
        if model is None:return {"ok":True,"payload":{"downloaded":True}}
        assert len(pcm)==2*m.CAPTURE_BYTES
        inference.append(model.name)
        return {"ok":True,"payload":{
            "local_cpu_model_loaded":True,
            "mic_used":False,"speaker_used":False,
            "measurements":rows(match=model.name==m.BASE_FOLDER),
            "peak_rss_mib":400.,
        }}
    monkeypatch.setattr(m,"_limited_child",worker)
    r=m.compare_alma_swedish(root,authorized=True,machine="aarch64")
    assert r["status"]=="pinned-piper-alma-whisper-comparison-complete"
    assert variants==[1.0,1.25]
    assert inference==[m.SMALL_FOLDER,m.BASE_FOLDER]
    assert r["piper_voice_sha256_verified"] is True
    assert r["piper_variants_run"]==2
    assert all(row["matched"] is False for row in r["tiny_results"])
    assert all(row["matched"] is True for row in r["base_results"])
    assert len(r["tiny_results"])==len(r["base_results"])==4
    exported=json.dumps(r)
    assert "decoded" not in exported.lower()
    assert "Vad heter du" not in exported
    assert "onnx" not in exported
    assert r["production_changed"] is False
    assert r["speaker_opened"] is False
    assert r["real_microphone_opened"] is False


def test_unrecognized_worker_data_never_reaches_report(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_limited_child",lambda *a,**kw:{
        "ok":True,"payload":{
            "local_cpu_model_loaded":True,
            "mic_used":False,"speaker_used":False,
            "measurements":[{"transcript":"PRIVATE RAW SPEECH"}],
        },
    })
    r=m.compare_alma_swedish(root,authorized=True,machine="aarch64")
    assert r["status"]=="invalid-tiny-measurement"
    assert "PRIVATE RAW SPEECH" not in json.dumps(r)


def test_voice_fetch_never_accepts_existing_directory(tmp_path):
    root=tmp_path/"already-present"
    root.mkdir()
    assert m._download_verified_voice(root) is False


def test_alma_weight_sha_and_piper_wheel_digests_are_pinned():
    assert len(m.VOICE_WEIGHTS_SHA256)==64
    assert m.VOICE_WEIGHTS_SHA256=="f75455eb6afeb1db9e2905d5bd7e4115afcd3710e0d399b6a40981766d32fedc"
    assert m.EXPECTED_PIPER_WHEEL_SHA256=="3f60c1917de6d8e8033f395878ad3f88f6dfee88a8b05f98971a275f76a38484"
    assert m.PINNED_VOICE_REVISION=="834f232"
    assert m.VOICE_SUBDIR=="sv/sv_SE/alma/medium"
    assert "Vad heter du?" in m._PIPER_RENDER


def test_does_not_open_or_store_audio_by_default():
    assert "arecord" not in m._PIPER_RENDER
    assert "aplay" not in m._PIPER_RENDER
    assert "with wave.open(buf" in m._PIPER_RENDER
    assert "output_file" not in m._PIPER_RENDER
