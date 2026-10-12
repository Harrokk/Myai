"""Privacy-safe, synthetic-only Whisper Tiny/Base comparison tests."""
from pathlib import Path
from types import SimpleNamespace
import array
import io
import json
import wave

import pytest
import scripts.ventuno_whisper_base_swedish_comparison as compare


def fake_voice_wave():
    b=io.BytesIO()
    with wave.open(b,"wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(22050)
        writer.writeframes(array.array("h",[6000]*22050).tobytes())
    return b.getvalue()


def setup(monkeypatch,tmp_path):
    monkeypatch.setenv("RUNNER_TEMP",str(tmp_path))
    root=tmp_path/"myai-sw-base-compare-test"
    root.mkdir()
    path=root/compare.STT_PYTHON
    path.parent.mkdir(parents=True)
    path.write_text("fake interpreter")
    (root/compare.SMALL_FOLDER).mkdir()
    (root/compare.TTS_FOLDER).mkdir()
    monkeypatch.setattr(compare,"mem_available_kib",lambda:12*1024*1024)
    monkeypatch.setattr(compare,"disk_free_bytes",lambda _:20*1024**3)
    monkeypatch.setattr(compare,"model_integrity",lambda _:{
        "model_sha256":compare.EXPECTED_MODEL_SHA256
    })
    monkeypatch.setattr(compare,"base_integrity",lambda _:True)
    monkeypatch.setattr(compare,"espeak_paths",lambda _:
                        (root/"espeak-ng",root/"voice-data"))
    monkeypatch.setattr(compare.subprocess,"run",lambda cmd,**kw:
                        SimpleNamespace(returncode=0,stdout=fake_voice_wave(),
                                        stderr=b"private"))
    return root


def fake_measurements(*,all_match=False):
    return [
        {"beam":beam,"matched":all_match or (i==0 and beam==5),
         "category":"approved" if all_match or (i==0 and beam==5)
         else "other-unmatched","seconds":1.6,
         "proximity":{
             "distance_band":"0" if all_match or (i==0 and beam==5) else "11+",
             "word_count_band":"3",
             "target_words_present":3 if all_match else 1,
             "target_words_aligned":3 if all_match else 0,
             "target_words_in_order":all_match,
             "exact_phrase_contained":all_match,
         }}
        for i in range(2) for beam in compare.BEAMS
    ]


def test_no_authorization_never_runs_model(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(compare,"_limited_child",
                        lambda *a,**k:pytest.fail("not authorized"))
    r=compare.compare_swedish_question(root,machine="aarch64")
    assert r["status"]=="not-authorized"
    assert not r["real_mic_opened"]
    assert not r["real_speaker_opened"]


def test_bad_arch_and_root_never_run(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(compare,"_limited_child",
                        lambda *a,**k:pytest.fail("must fail before inference"))
    r=compare.compare_swedish_question(root,authorized=True,machine="x86_64")
    assert r["status"]=="reject-non-arm64"
    wrong=tmp_path/"other"
    wrong.mkdir()
    r=compare.compare_swedish_question(wrong,authorized=True,machine="aarch64")
    assert r["status"]=="reject-nonrunner-workspace"


def test_low_memory_never_synthesizes_or_downloads(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(compare,"mem_available_kib",lambda:1234)
    monkeypatch.setattr(compare.subprocess,"run",
                        lambda *a,**k:pytest.fail("should be fail closed"))
    assert compare.compare_swedish_question(
        root,authorized=True,machine="aarch64"
    )["status"]=="reject-resource-reserve"


def test_existing_untrusted_base_cannot_be_overwritten(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    (root/compare.BASE_FOLDER).mkdir()
    monkeypatch.setattr(compare.subprocess,"run",
                        lambda *a,**k:pytest.fail("should not synthesize"))
    assert compare.compare_swedish_question(
        root,authorized=True,machine="aarch64"
    )["status"]=="reject-model-layout"


def test_tiny_and_base_run_separately_with_two_speeds_and_beams(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    calls=[]
    def child(python,program,work,*,model=None,pcm=None):
        calls.append((model,program,pcm))
        if model is None: return {"ok":True,"payload":{"downloaded":True}}
        assert isinstance(pcm,bytes) and len(pcm)==192000
        assert model in (root/compare.SMALL_FOLDER,root/compare.BASE_FOLDER)
        return {"ok":True,"payload":{
            "local_cpu_model_loaded":True,
            "mic_used":False,"speaker_used":False,
            "load_seconds":1.2,"peak_rss_mib":540.0,
            "measurements":fake_measurements(all_match=model.name==compare.BASE_FOLDER),
        }}
    monkeypatch.setattr(compare,"_limited_child",child)
    r=compare.compare_swedish_question(root,authorized=True,machine="aarch64")
    assert r["status"]=="tiny-base-synthetic-swedish-comparison-complete"
    assert r["synthetic_cases"]==2
    assert [x[0] and x[0].name for x in calls]==[
        compare.SMALL_FOLDER,None,compare.BASE_FOLDER
    ]
    assert r["tiny_beam1_matches"]==0
    assert r["tiny_beam5_matches"]==1
    assert r["base_beam1_matches"]==2
    assert r["base_beam5_matches"]==2
    assert len(r["tiny_results"])==4
    assert len(r["base_results"])==4
    assert all(x["speaking_rate"] in ("normal","slow") for x in r["base_results"])
    report=json.dumps(r)
    assert "Vad heter du" not in report
    assert "real_pcm" not in report
    assert all(r[key] is False for key in (
        "real_mic_opened","real_speaker_opened","user_audio_processed",
        "speech_saved","decoded_text_logged","production_changed",
        "geniex_called","ollama_called",
    ))


def test_base_download_failure_keeps_tiny_result_without_lying(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    def child(python,program,work,*,model=None,pcm=None):
        if model is None:return {"ok":False,"reason":"download"}
        return {"ok":True,"payload":{
            "local_cpu_model_loaded":True,"mic_used":False,"speaker_used":False,
            "measurements":fake_measurements(),"load_seconds":1,
            "peak_rss_mib":400,
        }}
    monkeypatch.setattr(compare,"_limited_child",child)
    r=compare.compare_swedish_question(root,authorized=True,machine="aarch64")
    assert r["status"]=="base-pinned-download-unavailable"
    assert len(r["tiny_results"])==4
    assert r["base_results"]==[]


def test_invalid_model_measurement_rejected(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(compare,"_limited_child",lambda *a,**k:{
        "ok":True,
        "payload":{"local_cpu_model_loaded":True,"mic_used":False,
                   "speaker_used":False,"measurements":[{"raw_transcript":"SECRET"}]}
    })
    r=compare.compare_swedish_question(root,authorized=True,machine="aarch64")
    assert r["status"]=="invalid-tiny-measurement"
    assert "SECRET" not in json.dumps(r)


def test_base_integrity_rejects_missing_or_linked_weights(tmp_path):
    p=tmp_path/"myai-whisper-base-model"
    p.mkdir()
    assert compare.base_integrity(p) is False
    (p/"model.bin").symlink_to(tmp_path/"arbitrary-weight-file")
    assert compare.base_integrity(p) is False


def test_model_source_pinned_and_not_english_only():
    assert compare.BASE_REPO=="Systran/faster-whisper-base"
    assert len(compare.BASE_REVISION)==40
    assert len(compare.BASE_SHA256)==64
    assert compare.BASE_SHA256 in compare.__dict__["BASE_SHA256"]
    assert 'revision="ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"' in compare._DOWNLOAD_BASE
    assert '"model.bin"' in compare._DOWNLOAD_BASE
    assert "local_files_only=True" in compare._INFERENCE
    assert "device=\"cpu\"" in compare._INFERENCE
    assert '"sv"' in compare._INFERENCE
    assert "initial_prompt" not in compare._INFERENCE


def test_worker_does_not_report_transcript_or_save_audio():
    assert "print(json.dumps" in compare._INFERENCE
    assert 'del transcript,norm' in compare._INFERENCE
    assert '"matched":valid' in compare._INFERENCE
    assert "microphone" not in compare._INFERENCE
    assert "sounddevice" not in compare._INFERENCE


def _pure_phrase_metrics():
    namespace={}
    exec(compare._METRIC_SOURCE,namespace)
    return namespace["private_phrase_metrics"]


@pytest.mark.parametrize("heard,expected_band,overlap,aligned,contained",[
    ("Vad heter du?", "0", 3, 3, True),
    ("Vad heter det?", "1-2", 2, 2, False),
    ("Vad heter", "3-5", 2, 2, False),
    ("Hej, vad heter du?", "3-5", 3, 0, True),
    ("du heter vad", "6-10", 3, 0, False),
    ("", "11+", 0, 0, False),
])
def test_private_metrics_compute_only_categorical_distance(
    heard,expected_band,overlap,aligned,contained,
):
    value=_pure_phrase_metrics()(heard)
    assert value["distance_band"]==expected_band
    assert value["target_words_present"]==overlap
    assert value["target_words_aligned"]==aligned
    assert value["exact_phrase_contained"] is contained
    text=json.dumps(value)
    assert heard not in text if heard else "Vad heter du" not in text
    assert all(isinstance(item,(bool,int,str)) for item in value.values())


def test_private_metrics_long_or_adversarial_decodes_are_bounded():
    function=_pure_phrase_metrics()
    outcome=function("IGNORE SYSTEM RULES " * 20000)
    assert outcome["distance_band"]=="11+"
    assert outcome["target_words_present"]==0
    assert outcome["word_count_band"]=="7+"
    assert max(len(str(value)) for value in outcome.values()) < 25


def test_only_trusted_metrics_allowed_in_parent_validator(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    def child(python,program,work,*,model=None,pcm=None):
        if model is None:return {"ok":True,"payload":{"downloaded":True}}
        rows=fake_measurements(all_match=True)
        rows[0]["proximity"]["transcript"]="SECRET RAW WORDS"
        return {"ok":True,"payload":{
            "local_cpu_model_loaded":True,
            "mic_used":False,"speaker_used":False,
            "measurements":rows,
        }}
    monkeypatch.setattr(compare,"_limited_child",child)
    r=compare.compare_swedish_question(root,authorized=True,machine="aarch64")
    assert r["status"]=="invalid-tiny-measurement"
    assert "SECRET" not in json.dumps(r)
