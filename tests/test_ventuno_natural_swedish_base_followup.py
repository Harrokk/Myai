"""Mock-only tests: public natural Swedish sound with pinned Whisper Base."""
import json
import pytest
import scripts.ventuno_natural_swedish_base_followup as m

def setup(monkeypatch,tmp_path):
    monkeypatch.setenv("RUNNER_TEMP",str(tmp_path))
    root=tmp_path/"myai-natural-sv-test-base"
    root.mkdir()
    (root/m.SMALL_FOLDER).mkdir()
    py=root/m.STT_PYTHON
    py.parent.mkdir(parents=True,exist_ok=True)
    py.write_text("fake")
    monkeypatch.setattr(m,"mem_available_kib",lambda:12*1024*1024)
    monkeypatch.setattr(m,"disk_free_bytes",lambda _:12*1024**3)
    monkeypatch.setattr(m,"model_integrity",lambda _:{"model_sha256":m.EXPECTED_MODEL_SHA256})
    monkeypatch.setattr(m,"base_integrity",lambda _:True)
    monkeypatch.setattr(m,"_fetch_human_audio",lambda:b"pinned-public-human-ogg")
    return root

def rows():
    return [
        {"variant":case,"beam":beam,"matched":beam==5,
         "distance_band":"0" if beam==5 else "3-5",
         "target_words_present":3 if beam==5 else 1,
         "target_words_in_order":beam==5,"seconds":1.}
        for case in ("original","three-second-capture")
        for beam in (1,5)
    ]

def mock_worker(interpreter,source,root,*,model=None,pcm=None):
    if model is None:
        return {"ok":True,"payload":{"downloaded":True}}
    assert pcm==b"pinned-public-human-ogg"
    assert model.name==m.BASE_FOLDER
    assert "decode_audio" in source
    return {"ok":True,"payload":{
        "model_loaded":True,"microphone_opened":False,
        "speaker_opened":False,"user_audio_processed":False,
        "transcript_persisted":False,"cases":rows(),"peak_rss_mib":340.,
    }}

def test_explicit_authorization_required(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_fetch_human_audio",lambda:pytest.fail("must not download"))
    r=m.compare_human_base(root,machine="aarch64")
    assert r["status"]=="not-authorized"
    assert r["real_microphone_opened"] is False

def test_wrong_architecture(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    r=m.compare_human_base(root,authorized=True,machine="x86_64")
    assert r["status"]=="blocked-architecture"

def test_workspace_rejected(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    wrong=tmp_path/"not-runner"
    wrong.mkdir()
    r=m.compare_human_base(wrong,authorized=True,machine="aarch64")
    assert r["status"]=="blocked-nonisolated-workspace"

def test_no_memory_blocks_download(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"mem_available_kib",lambda:0)
    r=m.compare_human_base(root,authorized=True,machine="aarch64")
    assert r["status"]=="blocked-resource-gate"

def test_failed_fixture_does_not_download_weights(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_fetch_human_audio",lambda:None)
    monkeypatch.setattr(m,"_limited_child",lambda *a,**kw:pytest.fail("no inference"))
    r=m.compare_human_base(root,authorized=True,machine="aarch64")
    assert r["status"]=="blocked-human-fixture-integrity"

def test_existing_base_folder_blocks_overwrite(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    (root/m.BASE_FOLDER).mkdir()
    r=m.compare_human_base(root,authorized=True,machine="aarch64")
    assert r["status"]=="blocked-model-layout"

def test_base_hash_must_match_before_worker(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"base_integrity",lambda _:False)
    monkeypatch.setattr(m,"_limited_child",mock_worker)
    r=m.compare_human_base(root,authorized=True,machine="aarch64")
    assert r["status"]=="base-weight-download-or-hash-failed"

def test_four_public_cases_with_base_and_no_transcripts(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    monkeypatch.setattr(m,"_limited_child",mock_worker)
    r=m.compare_human_base(root,authorized=True,machine="aarch64")
    assert r["status"]=="pinned-human-swedish-base-comparison-complete"
    assert len(r["base_results"])==4
    assert r["base_sha256_verified"]
    assert r["human_fixture_sha256_verified"]
    assert r["baseline_tiny_sha256_verified"]
    assert [x["matched"] for x in r["base_results"]]==[False,True,False,True]
    assert "decoded" not in json.dumps(r)
    assert "raw transcript text" not in json.dumps(r)
    assert r["geniex_called"] is False
    assert r["production_changed"] is False

def test_malicious_raw_transcript_field_never_logged(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    def malicious(py,source,root,*,model=None,pcm=None):
        if model is None:return {"ok":True,"payload":{"downloaded":True}}
        case=rows()
        case[0]["raw_transcript"]="SECRET"
        return {"ok":True,"payload":{
            "model_loaded":True,"microphone_opened":False,
            "speaker_opened":False,"user_audio_processed":False,
            "transcript_persisted":False,"cases":case,
        }}
    monkeypatch.setattr(m,"_limited_child",malicious)
    r=m.compare_human_base(root,authorized=True,machine="aarch64")
    assert r["status"]=="invalid-base-case"
    assert "SECRET" not in json.dumps(r)

def test_incorrect_envelope_rejected(monkeypatch,tmp_path):
    root=setup(monkeypatch,tmp_path)
    def malicious(py,source,root,*,model=None,pcm=None):
        if model is None:return {"ok":True,"payload":{"downloaded":True}}
        return {"ok":True,"payload":{
            "model_loaded":True,"microphone_opened":True,
            "speaker_opened":False,"user_audio_processed":False,
            "transcript_persisted":False,"cases":rows(),
        }}
    monkeypatch.setattr(m,"_limited_child",malicious)
    r=m.compare_human_base(root,authorized=True,machine="aarch64")
    assert r["status"]=="invalid-base-envelope"
