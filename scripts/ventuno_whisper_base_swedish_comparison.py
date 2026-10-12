"""CPU-only controlled Whisper Tiny versus Base Swedish short question test.

Requires previously staged, checksum-verified Whisper Tiny and Swedish
eSpeak NG. Downloads only a pinned multilingual Whisper Base CT2 model
into the runner's private temporary directory, SHA-256-verifies the
actual weights, then transcribes 2 synthetic Swedish utterances at two
beam sizes using both CPU models in SEPARATE bounded worker processes.

No microphone, loudspeaker, Ollama/GenieX calls, production writes,
raw transcription logs, or saved WAV/PCM. Outputs only booleans, timing
and allowlisted coarse recognition categories. No expected text is
passed to the inference model as an initial prompt.
"""
from __future__ import annotations

import array
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

from scripts.ventuno_synthetic_swedish_question_stt import (
    PHRASE, SPEEDS, wav_to_three_second_capture,
)
from scripts.ventuno_tts_temp_stage import espeak_paths
from scripts.ventuno_voice_wheel_staging import mem_available_kib, disk_free_bytes
from scripts.ventuno_whisper_tiny_cpu_smoke import (
    MAX_AS_BYTES, MAX_CPU_SECONDS, MIN_MEM_AVAILABLE_KIB,
    MIN_DISK_AVAILABLE_BYTES, EXPECTED_MODEL_SHA256, model_integrity,
)

BASE_REPO = "Systran/faster-whisper-base"
BASE_REVISION = "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"
BASE_SHA256 = "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9"
MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
BASE_FOLDER = "myai-whisper-base-model"
SMALL_FOLDER = "myai-whisper-tiny-model"
STT_PYTHON = "myai-voice-staging/bin/python"
TTS_FOLDER = "myai-tts-espeak-stage"
BEAMS = (1, 5)
CASE_BYTES = 96000
MAX_DOWNLOAD_SECONDS = 360
MAX_INFERENCE_SECONDS = 175
MIN_FREED_RAM_KIB = 4 * 1024 * 1024

_DOWNLOAD_BASE = r"""
import json
import os
from pathlib import Path
from huggingface_hub import snapshot_download

root=Path(os.environ["MYAI_TEST_BASE_FOLDER"])
p=snapshot_download(
    repo_id="Systran/faster-whisper-base",
    revision="ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
    allow_patterns=["config.json","model.bin","tokenizer.json","vocabulary.txt"],
    local_dir=str(root),max_workers=2,token=False,
)
assert Path(p).resolve() == root.resolve()
print(json.dumps({"downloaded":True}))
"""

# The worker never emits or persists transcriptions, even of synthetic
# audio. It receives exactly two case PCM buffers and exits before
# loading another model, preventing simultaneous Tiny+Base RAM use.
_INFERENCE = r"""
import json,os,re,resource,sys,time
import numpy as np
from faster_whisper import WhisperModel

raw=sys.stdin.buffer.read(192001)
if len(raw)!=192000:
    raise ValueError("wrong-two-case-synthetic-input-size")
audio=[
    np.frombuffer(raw[pos:pos+96000],dtype="<i2").astype(np.float32)/32768.0
    for pos in (0,96000)
]
start=time.monotonic()
model=WhisperModel(
    os.environ["MYAI_TEST_MODEL_PATH"],
    device="cpu",compute_type="int8",
    cpu_threads=2,num_workers=1,local_files_only=True,
)
load_seconds=round(time.monotonic()-start,3)
out=[]
for speech in audio:
    for beam in (1,5):
        start=time.monotonic()
        segments,info=model.transcribe(
            speech,language="sv",task="transcribe",
            beam_size=beam,best_of=1,
            condition_on_previous_text=False,
            vad_filter=False,without_timestamps=True,
            no_speech_threshold=0.6,
        )
        transcript=" ".join(segment.text for segment in segments)
        norm=re.sub(r"\s+"," ",re.sub(r"[^0-9a-zåäö ]+"," ",transcript.lower())).strip()
        valid=norm == "vad heter du"
        if valid: category="approved"
        elif not norm: category="empty"
        elif len(norm.split())<=2: category="short-unmatched"
        else: category="other-unmatched"
        out.append({
            "beam":beam,
            "matched":valid,
            "category":category,
            "seconds":round(time.monotonic()-start,3),
        })
        # Delete the only references to decoded words before next case.
        del transcript,norm,segments,info
print(json.dumps({
    "local_cpu_model_loaded":True,
    "load_seconds":load_seconds,
    "measurements":out,
    "peak_rss_mib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
    "mic_used":False,"speaker_used":False,
}))
"""


def base_integrity(directory: Path) -> bool:
    """Fail closed unless the exact pinned Base CT2 weights are present."""
    if directory.is_symlink() or not directory.is_dir():
        return False
    try:
        sizes = {}
        for name in MODEL_FILES:
            p=directory/name
            if p.is_symlink() or not p.is_file():
                return False
            sizes[name] = p.stat().st_size
        if not (135_000_000 <= sizes["model.bin"] <= 155_000_000):
            return False
        if not (0 < sizes["config.json"] < 100_000
                and 0 < sizes["tokenizer.json"] < 6_000_000
                and 0 < sizes["vocabulary.txt"] < 2_000_000):
            return False
        if sum(sizes.values()) > 166_000_000:
            return False
        config=json.loads((directory/"config.json").read_text(encoding="utf-8"))
        if not isinstance(config,dict) or len(config)>120:
            return False
        with (directory/"model.bin").open("rb") as stream:
            return hashlib.file_digest(stream,"sha256").hexdigest()==BASE_SHA256
    except (OSError, ValueError, TypeError):
        return False


def _limited_child(
    interpreter: Path, source: str, root: Path, *,
    model: Path | None = None, pcm: bytes | None = None,
) -> dict[str, object]:
    import resource
    env=os.environ.copy()
    env.update({
        "HF_HOME":str(root/"myai-whisper-hf-cache"),
        "XDG_CACHE_HOME":str(root/"myai-whisper-hf-cache"),
        "HF_HUB_DISABLE_TELEMETRY":"1",
        "HF_HUB_DISABLE_PROGRESS_BARS":"1",
        "TOKENIZERS_PARALLELISM":"false",
        "PYTHONDONTWRITEBYTECODE":"1",
        "OMP_NUM_THREADS":"2",
        "OPENBLAS_NUM_THREADS":"1",
    })
    if model is None:
        env["MYAI_TEST_BASE_FOLDER"]=str(root/BASE_FOLDER)
        timeout=MAX_DOWNLOAD_SECONDS
    else:
        env.update({
            "MYAI_TEST_MODEL_PATH":str(model),
            "HF_HUB_OFFLINE":"1",
            "TRANSFORMERS_OFFLINE":"1",
        })
        timeout=MAX_INFERENCE_SECONDS

    def restrict() -> None:
        resource.setrlimit(resource.RLIMIT_AS,(MAX_AS_BYTES,MAX_AS_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU,(MAX_CPU_SECONDS,MAX_CPU_SECONDS))
    try:
        proc=subprocess.run(
            [str(interpreter),"-I","-c",source],input=pcm,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=root,env=env,check=False,timeout=timeout,
            preexec_fn=restrict if model is not None else None,
        )
    except (OSError,subprocess.TimeoutExpired):
        return {"ok":False,"reason":"timeout-or-launch-failed"}
    if proc.returncode or len(proc.stdout)>4096:
        return {"ok":False,"reason":"child-failed-or-output-oversize"}
    try:
        response=json.loads(proc.stdout)
    except (ValueError,TypeError):
        return {"ok":False,"reason":"invalid-child-json"}
    if not isinstance(response,dict):
        return {"ok":False,"reason":"invalid-child-shape"}
    # Never expose subprocess stderr or unexpected response fields.
    return {"ok":True,"payload":response}


def compare_swedish_question(root: Path, *, authorized: bool = False,
                             machine: str | None = None) -> dict[str, object]:
    report:dict[str,object]={
        "status":"not-authorized",
        "tiny_beam1_matches":0,
        "tiny_beam5_matches":0,
        "base_beam1_matches":0,
        "base_beam5_matches":0,
        "synthetic_cases":0,
        "tiny_results":[],
        "base_results":[],
        "real_mic_opened":False,
        "real_speaker_opened":False,
        "user_audio_processed":False,
        "speech_saved":False,
        "decoded_text_logged":False,
        "production_changed":False,
        "geniex_called":False,
        "ollama_called":False,
    }
    if not authorized:
        return report
    if (machine or platform.machine()).lower() not in ("arm64","aarch64"):
        report["status"]="reject-non-arm64"
        return report
    runner_temp=os.environ.get("RUNNER_TEMP","")
    try:
        if (not runner_temp or root.is_symlink() or
                root.resolve(strict=True).parent != Path(runner_temp).resolve(strict=True)
                or not root.name.startswith("myai-sw-base-compare-")):
            report["status"]="reject-nonrunner-workspace"
            return report
    except OSError:
        report["status"]="reject-nonrunner-workspace"
        return report
    if (mem_available_kib() or 0)<MIN_MEM_AVAILABLE_KIB or (
            disk_free_bytes(root) or 0)<MIN_DISK_AVAILABLE_BYTES:
        report["status"]="reject-resource-reserve"
        return report
    python=root/STT_PYTHON
    tiny=root/SMALL_FOLDER
    voice=root/TTS_FOLDER
    base=root/BASE_FOLDER
    if not python.is_file() or not tiny.is_dir() or base.exists() or base.is_symlink():
        report["status"]="reject-model-layout"
        return report
    if model_integrity(tiny).get("model_sha256")!=EXPECTED_MODEL_SHA256:
        report["status"]="reject-unverified-tiny"
        return report
    executable,voice_data=espeak_paths(voice)
    if executable is None or voice_data is None:
        report["status"]="reject-unverified-swedish-tts"
        return report
    env=os.environ.copy()
    env["LD_LIBRARY_PATH"]=(
        str(voice/"extracted/usr/lib/aarch64-linux-gnu")
        +os.pathsep+env.get("LD_LIBRARY_PATH","")
    )
    cases=[]
    for speed in SPEEDS:
        try:
            proc=subprocess.run(
                [str(executable),"--path="+str(voice_data.parent),
                 "-v","sv","-s",str(speed),"--stdout",PHRASE],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                cwd=voice,env=env,check=False,timeout=10,
            )
        except (OSError,subprocess.TimeoutExpired):
            report["status"]="synthetic-voice-failed"
            return report
        if proc.returncode:
            report["status"]="synthetic-voice-failed"
            return report
        pcm=wav_to_three_second_capture(proc.stdout)
        if pcm is None or len(pcm)!=CASE_BYTES:
            report["status"]="synthetic-voice-invalid-pcm"
            return report
        cases.append(pcm)
        del pcm,proc
    report["synthetic_cases"]=len(cases)
    combined=b"".join(cases)
    del cases
    for model_name,model_path in (("tiny",tiny),("base",base)):
        if (mem_available_kib() or 0)<MIN_FREED_RAM_KIB:
            report["status"]="reject-inference-ram"
            return report
        if model_name=="base":
            download=_limited_child(python,_DOWNLOAD_BASE,root)
            if not download["ok"] or download["payload"].get("downloaded") is not True:
                report["status"]="base-pinned-download-unavailable"
                return report
            if not base_integrity(base):
                report["status"]="base-pinned-model-integrity-failed"
                return report
        child=_limited_child(python,_INFERENCE,root,model=model_path,pcm=combined)
        if not child["ok"]:
            report["status"]=model_name+"-cpu-inference-failed"
            return report
        p=child["payload"]
        values=p.get("measurements")
        if (p.get("local_cpu_model_loaded") is not True
                or p.get("mic_used") is not False
                or p.get("speaker_used") is not False
                or not isinstance(values,list) or len(values)!=4):
            report["status"]="invalid-"+model_name+"-measurement"
            return report
        validated=[]
        for idx,entry in enumerate(values):
            if (not isinstance(entry,dict)
                    or entry.get("beam")!=BEAMS[idx%2]
                    or type(entry.get("matched")) is not bool
                    or entry.get("category") not in (
                        "approved","empty","short-unmatched","other-unmatched"
                    )
                    or type(entry.get("seconds")) not in (float,int)
                    or not 0<=entry["seconds"]<=MAX_INFERENCE_SECONDS):
                report["status"]="invalid-"+model_name+"-measurement"
                return report
            validated.append({
                "speaking_rate":("normal" if idx<2 else "slow"),
                "beam":entry["beam"],
                "matched":entry["matched"],
                "category":entry["category"],
                "seconds":entry["seconds"],
            })
        report[model_name+"_results"]=validated
        report[model_name+"_beam1_matches"]=sum(
            x["matched"] for x in validated if x["beam"]==1
        )
        report[model_name+"_beam5_matches"]=sum(
            x["matched"] for x in validated if x["beam"]==5
        )
        report[model_name+"_load_seconds"]=p.get("load_seconds")
        report[model_name+"_peak_rss_mib"]=p.get("peak_rss_mib")
    report["status"]="tiny-base-synthetic-swedish-comparison-complete"
    return report


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp",required=True,type=Path)
    parser.add_argument("--compare-offline-models",action="store_true")
    args=parser.parse_args()
    result=compare_swedish_question(
        args.runner_temp,authorized=args.compare_offline_models,
    )
    print("Synthetic Whisper Tiny/Base Swedish question comparison:",
          json.dumps(result,sort_keys=True))
    return 0 if result["status"] in (
        "not-authorized","tiny-base-synthetic-swedish-comparison-complete",
    ) else 2


if __name__=="__main__":
    raise SystemExit(main())
