"""Evaluate public human Swedish speech through pinned Whisper Tiny on VENTUNO.

The reference utterance is "hur mår du?", not the previously synthesized
"vad heter du?". It is an independently human-spoken Shtooka Project
recording from a Swedish speaker from Gotland. Source: Wikimedia Commons
*archived old file revision*, CC BY 2.0 France, M. Kihlstedt / N. Vion.

All downloads/models/inference live only in a disposable GitHub-runner
directory; the worker emits ONLY sanitized distance bands and match flags.
No user microphone, speaker, saved raw speech, persistent model install,
GenieX, Ollama, audio service or production config is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from urllib.request import Request, urlopen

from scripts.ventuno_whisper_base_swedish_comparison import (
    _limited_child, MAX_INFERENCE_SECONDS, MIN_FREED_RAM_KIB,
    SMALL_FOLDER, STT_PYTHON, EXPECTED_MODEL_SHA256, model_integrity,
)
from scripts.ventuno_whisper_tiny_cpu_smoke import (
    MIN_MEM_AVAILABLE_KIB, MIN_DISK_AVAILABLE_BYTES,
)
from scripts.ventuno_voice_wheel_staging import mem_available_kib, disk_free_bytes

# Wikimedia Commons source page:
# https://commons.wikimedia.org/wiki/File:Sv-(conversation).ogg
# Old revision 2007-11-06 (description "hur mår du?"), 1.3 s.
# Source recording CC BY 2.0 France, M. Kihlstedt / N. Vion.
SOURCE = (
    "https://upload.wikimedia.org/wikipedia/commons/archive/1/1d/"
    "20071106020716%21Sv-%28conversation%29.ogg"
)
EXPECTED_SHA256 = "e83b36079bcd2c001c0a8466961f503923bdbb7e5fb14e6d5f93e981bc636e4b"
EXPECTED_BYTES = 15152
MAX_BYTES = 32000
TARGET = "hur mår du"
BEAMS = (1, 5)
MAX_RSS_MIB = 4096

_HUMAN_WORKER = r"""
import hashlib,io,json,os,re,resource,sys,time
import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

raw=sys.stdin.buffer.read(32001)
if len(raw)!=15152 or hashlib.sha256(raw).hexdigest()!="e83b36079bcd2c001c0a8466961f503923bdbb7e5fb14e6d5f93e981bc636e4b":
    raise ValueError("human-reference-integrity-failed")
spoken=decode_audio(io.BytesIO(raw),sampling_rate=16000)
if spoken.ndim!=1 or not 6000<=len(spoken)<=48000:
    raise ValueError("public-audio-duration-invalid")
spoken=np.asarray(spoken,dtype=np.float32)
level=float(np.sqrt(np.mean(np.square(spoken))))
if not 0.003<=level<=0.95:
    raise ValueError("public-human-audio-signal-invalid")
# Also simulate physical capture: 350 ms before speech and 3 s total.
capture=np.zeros(48000,dtype=np.float32)
n=min(len(spoken),48000-5600)
capture[5600:5600+n]=spoken[:n]
start=time.monotonic()
model=WhisperModel(
    os.environ["MYAI_TEST_MODEL_PATH"],
    device="cpu",compute_type="int8",cpu_threads=2,num_workers=1,
    local_files_only=True,
)
load_s=round(time.monotonic()-start,3)
expected="hur mår du"
def distance(a,b,cap=11):
    if abs(len(a)-len(b))>=cap: return cap
    row=list(range(len(b)+1))
    for ix,left in enumerate(a,1):
        new=[ix]
        for j,right in enumerate(b,1):
            new.append(min(new[j-1]+1,row[j]+1,row[j-1]+(left!=right)))
        row=new
    return min(row[-1],cap)

results=[]
for variant,audio in (("original",spoken),("three-second-capture",capture)):
    for beam in (1,5):
        start=time.monotonic()
        segments,meta=model.transcribe(
            audio,language="sv",task="transcribe",beam_size=beam,best_of=1,
            condition_on_previous_text=False,vad_filter=False,
            without_timestamps=True,no_speech_threshold=0.6,
        )
        decoded=" ".join(seg.text for seg in segments)
        normalized=re.sub(r"\s+"," ",re.sub(r"[^0-9a-zåäö ]+"," ",decoded.lower())).strip()[:128]
        dist=distance(normalized,expected)
        words=normalized.split()
        count=sum(w in words for w in ("hur","mår","du"))
        ordered=iter(words)
        in_order=all(any(x==w for x in ordered) for w in ("hur","mår","du"))
        band=("0" if dist==0 else "1-2" if dist<=2 else "3-5" if dist<=5
              else "6-10" if dist<=10 else "11+")
        results.append({
            "variant":variant,"beam":beam,"matched":dist==0,
            "distance_band":band,"target_words_present":count,
            "target_words_in_order":in_order,
            "seconds":round(time.monotonic()-start,3),
        })
        del decoded,normalized,words,segments,meta
print(json.dumps({
    "model_loaded":True,"model_load_seconds":load_s,
    "cases":results,
    "peak_rss_mib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
    "microphone_opened":False,"speaker_opened":False,
    "user_audio_processed":False,"transcript_persisted":False,
}))
"""

def validate_public_recording(data: bytes) -> bool:
    return (len(data) == EXPECTED_BYTES and data[:4] == b"OggS"
            and hashlib.sha256(data).hexdigest() == EXPECTED_SHA256)


def _fetch_human_audio() -> bytes | None:
    try:
        req=Request(SOURCE,headers={"User-Agent":"MyAI-licensed-Swedish-human-STT/1.0"})
        with urlopen(req,timeout=30) as handle:
            if handle.geturl()!=SOURCE:
                return None
            data=handle.read(MAX_BYTES+1)
        return data if validate_public_recording(data) else None
    except (OSError,ValueError,TimeoutError):
        return None


def compare_human_swedish(root: Path, *, authorized: bool=False,
                          machine: str | None=None) -> dict[str,object]:
    report:dict[str,object]={
        "status":"not-authorized",
        "fixture_sha256_verified":False,
        "source":"Wikimedia Commons archived Shtooka human Swedish speech",
        "reference_phrase":"hur mår du",
        "tiny_results":[],
        "microphone_opened":False,"speaker_opened":False,
        "user_audio_processed":False,"transcripts_logged":False,
        "speech_saved":False,"production_changed":False,
        "geniex_called":False,"ollama_called":False,
    }
    if not authorized:
        return report
    if (machine or platform.machine()).lower() not in ("aarch64","arm64"):
        report["status"]="blocked-architecture"
        return report
    scratch=os.environ.get("RUNNER_TEMP","")
    try:
        if (not scratch or root.is_symlink() or
                root.resolve(strict=True).parent!=Path(scratch).resolve(strict=True)
                or not root.name.startswith("myai-natural-sv-")):
            report["status"]="blocked-nonisolated-workspace"
            return report
    except (OSError,ValueError):
        report["status"]="blocked-nonisolated-workspace"
        return report
    if ((mem_available_kib() or 0)<MIN_MEM_AVAILABLE_KIB or
            (disk_free_bytes(root) or 0)<MIN_DISK_AVAILABLE_BYTES):
        report["status"]="blocked-resource-gate"
        return report
    stt_py=root/STT_PYTHON
    model=root/SMALL_FOLDER
    if (not stt_py.is_file() or
            model_integrity(model).get("model_sha256")!=EXPECTED_MODEL_SHA256):
        report["status"]="blocked-unverified-whisper-tiny"
        return report
    raw=_fetch_human_audio()
    if raw is None:
        report["status"]="public-human-audio-download-or-hash-failed"
        return report
    report["fixture_sha256_verified"]=True
    if (mem_available_kib() or 0)<MIN_FREED_RAM_KIB:
        report["status"]="blocked-pre-inference-ram"
        return report
    worker=_limited_child(stt_py,_HUMAN_WORKER,root,model=model,pcm=raw)
    del raw
    if not worker["ok"]:
        report["status"]="human-voice-inference-failed"
        return report
    payload=worker["payload"]
    cases=payload.get("cases")
    if (payload.get("model_loaded") is not True or
            payload.get("microphone_opened") is not False or
            payload.get("speaker_opened") is not False or
            payload.get("user_audio_processed") is not False or
            payload.get("transcript_persisted") is not False or
            not isinstance(cases,list) or len(cases)!=4):
        report["status"]="invalid-worker-envelope"
        return report
    clean=[]
    for ix,item in enumerate(cases):
        if (not isinstance(item,dict) or
                set(item)!={"variant","beam","matched","distance_band",
                           "target_words_present","target_words_in_order","seconds"} or
                item["variant"]!=("original" if ix<2 else "three-second-capture") or
                item["beam"]!=BEAMS[ix%2] or
                type(item["matched"]) is not bool or
                item["distance_band"] not in ("0","1-2","3-5","6-10","11+") or
                type(item["target_words_present"]) is not int or
                not 0<=item["target_words_present"]<=3 or
                type(item["target_words_in_order"]) is not bool or
                type(item["seconds"]) not in (int,float) or
                not 0<=item["seconds"]<=MAX_INFERENCE_SECONDS):
            report["status"]="invalid-worker-case"
            return report
        clean.append({
            "variant":item["variant"],"beam":item["beam"],
            "matched":item["matched"],"distance_band":item["distance_band"],
            "target_words_present":item["target_words_present"],
            "target_words_in_order":item["target_words_in_order"],
        })
    report["tiny_results"]=clean
    peak=payload.get("peak_rss_mib")
    if type(peak) in (float,int) and 0<=peak<=MAX_RSS_MIB:
        report["tiny_peak_rss_mib"]=peak
    report["status"]="licensed-human-swedish-tiny-comparison-complete"
    return report


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp",required=True,type=Path)
    parser.add_argument("--allow-public-human-reference-only",action="store_true")
    args=parser.parse_args()
    result=compare_human_swedish(
        args.runner_temp,authorized=args.allow_public_human_reference_only,
    )
    print("Pinned licensed human Swedish reference to Tiny:",
          json.dumps(result,sort_keys=True))
    return 0 if result["status"] in (
        "not-authorized","licensed-human-swedish-tiny-comparison-complete"
    ) else 2


if __name__=="__main__":
    raise SystemExit(main())
