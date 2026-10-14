"""Compare pinned multilingual Whisper Base with Tiny on licensed human Swedish.

Uses the exact same SHA256-verified 1.3s human recording as the prior Tiny
experiment. Stages immutable Base weights into disposable runner workspace.
No new microphone permissions, audio devices, production changes, or logs
of recognized raw transcripts. Keep interpretation separate from Piper TTS.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path

from scripts.ventuno_natural_swedish_stt import (
    _fetch_human_audio, _HUMAN_WORKER, SOURCE, EXPECTED_SHA256,
    SMALL_FOLDER, STT_PYTHON, MAX_RSS_MIB, MAX_INFERENCE_SECONDS,
    BEAMS, EXPECTED_MODEL_SHA256, model_integrity,
)
from scripts.ventuno_whisper_base_swedish_comparison import (
    _limited_child, _DOWNLOAD_BASE, base_integrity,
    BASE_FOLDER, MIN_FREED_RAM_KIB, MIN_MEM_AVAILABLE_KIB,
    MIN_DISK_AVAILABLE_BYTES,
)
from scripts.ventuno_voice_wheel_staging import mem_available_kib, disk_free_bytes


def compare_human_base(root: Path, *, authorized: bool=False,
                       machine: str | None=None) -> dict[str,object]:
    report:dict[str,object]={
        "status":"not-authorized",
        "human_fixture_sha256_verified":False,
        "base_sha256_verified":False,
        "baseline_tiny_sha256_verified":False,
        "reference_phrase":"hur mår du",
        "base_results":[],
        "real_microphone_opened":False,"speaker_opened":False,
        "user_audio_processed":False,"raw_transcripts_logged":False,
        "speech_saved":False,"production_changed":False,
        "geniex_called":False,"ollama_called":False,
    }
    if not authorized:return report
    if (machine or platform.machine()).lower() not in ("arm64","aarch64"):
        report["status"]="blocked-architecture"
        return report
    scratch=os.environ.get("RUNNER_TEMP","")
    try:
        if (not scratch or root.is_symlink()
                or root.resolve(strict=True).parent!=Path(scratch).resolve(strict=True)
                or not root.name.startswith("myai-natural-sv-")):
            report["status"]="blocked-nonisolated-workspace"
            return report
    except (OSError,ValueError):
        report["status"]="blocked-nonisolated-workspace"
        return report
    if ((mem_available_kib() or 0)<MIN_MEM_AVAILABLE_KIB
            or (disk_free_bytes(root) or 0)<MIN_DISK_AVAILABLE_BYTES):
        report["status"]="blocked-resource-gate"
        return report
    tiny=root/SMALL_FOLDER
    base=root/BASE_FOLDER
    stt_py=root/STT_PYTHON
    if (not stt_py.is_file() or base.exists() or base.is_symlink()
            or model_integrity(tiny).get("model_sha256")!=EXPECTED_MODEL_SHA256):
        report["status"]="blocked-model-layout"
        return report
    report["baseline_tiny_sha256_verified"]=True
    # Re-download immutable public audio only; never use a user's microphone.
    audio=_fetch_human_audio()
    if audio is None:
        report["status"]="blocked-human-fixture-integrity"
        return report
    report["human_fixture_sha256_verified"]=True
    if (mem_available_kib() or 0)<MIN_FREED_RAM_KIB:
        report["status"]="blocked-pre-download-memory"
        return report
    download=_limited_child(stt_py,_DOWNLOAD_BASE,root)
    if (not download["ok"]
            or download["payload"].get("downloaded") is not True
            or not base_integrity(base)):
        report["status"]="base-weight-download-or-hash-failed"
        return report
    report["base_sha256_verified"]=True
    if (mem_available_kib() or 0)<MIN_FREED_RAM_KIB:
        report["status"]="blocked-pre-inference-memory"
        return report
    outcome=_limited_child(stt_py,_HUMAN_WORKER,root,model=base,pcm=audio)
    del audio
    if not outcome["ok"]:
        report["status"]="base-human-inference-failed"
        return report
    payload=outcome["payload"]
    rows=payload.get("cases")
    if (payload.get("model_loaded") is not True or
            payload.get("microphone_opened") is not False or
            payload.get("speaker_opened") is not False or
            payload.get("user_audio_processed") is not False or
            payload.get("transcript_persisted") is not False or
            not isinstance(rows,list) or len(rows)!=4):
        report["status"]="invalid-base-envelope"
        return report
    clean=[]
    for ix,item in enumerate(rows):
        if (not isinstance(item,dict)
                or set(item)!={"variant","beam","matched","distance_band",
                               "target_words_present","target_words_in_order","seconds"}
                or item["variant"]!=("original" if ix<2 else "three-second-capture")
                or item["beam"]!=BEAMS[ix%2]
                or type(item["matched"]) is not bool
                or item["distance_band"] not in ("0","1-2","3-5","6-10","11+")
                or type(item["target_words_present"]) is not int
                or not 0<=item["target_words_present"]<=3
                or type(item["target_words_in_order"]) is not bool
                or type(item["seconds"]) not in (int,float)
                or not 0<=item["seconds"]<=MAX_INFERENCE_SECONDS):
            report["status"]="invalid-base-case"
            return report
        clean.append({
            "variant":item["variant"],"beam":item["beam"],
            "matched":item["matched"],"distance_band":item["distance_band"],
            "target_words_present":item["target_words_present"],
            "target_words_in_order":item["target_words_in_order"],
        })
    report["base_results"]=clean
    rss=payload.get("peak_rss_mib")
    if type(rss) in (int,float) and 0<=rss<=MAX_RSS_MIB:
        report["base_peak_rss_mib"]=rss
    report["status"]="pinned-human-swedish-base-comparison-complete"
    return report


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp",required=True,type=Path)
    parser.add_argument("--allow-licensed-human-audio-only",action="store_true")
    args=parser.parse_args()
    report=compare_human_base(args.runner_temp,
        authorized=args.allow_licensed_human_audio_only)
    print("Pinned public human Swedish reference versus Base:",
          json.dumps(report,sort_keys=True))
    return 0 if report["status"] in (
        "not-authorized","pinned-human-swedish-base-comparison-complete"
    ) else 2


if __name__=="__main__":
    raise SystemExit(main())
