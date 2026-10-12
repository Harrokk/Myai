"""Isolated Piper Alma synthetic Swedish STT controls on VENTUNO Q.

Never accesses USB audio, user recordings, Ollama, GenieX or production
configuration. All model, Piper WAV and Whisper transcripts stay in
transient workspace/process memory; only sanitized comparison metrics
reach stdout. An incompatible runtime or checksum mismatch fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
from pathlib import Path
from urllib.request import urlopen

from scripts.ventuno_whisper_base_swedish_comparison import (
    _limited_child, _DOWNLOAD_BASE, _INFERENCE, base_integrity,
    MIN_FREED_RAM_KIB, MIN_MEM_AVAILABLE_KIB, MIN_DISK_AVAILABLE_BYTES,
    BEAMS, SMALL_FOLDER, BASE_FOLDER, STT_PYTHON, MAX_INFERENCE_SECONDS,
    EXPECTED_MODEL_SHA256, model_integrity,
)
from scripts.ventuno_synthetic_swedish_question_stt import (
    CAPTURE_BYTES, wav_to_three_second_capture, classify_pcm_quality,
)
from scripts.ventuno_voice_wheel_staging import mem_available_kib, disk_free_bytes

PINNED_VOICE_REVISION = "834f232"
HF_ROOT = "https://huggingface.co/rhasspy/piper-voices/resolve/"
VOICE_SUBDIR = "sv/sv_SE/alma/medium"
VOICE_MODEL = "sv_SE-alma-medium.onnx"
VOICE_CONFIG = "sv_SE-alma-medium.onnx.json"
VOICE_WEIGHTS_SHA256 = "f75455eb6afeb1db9e2905d5bd7e4115afcd3710e0d399b6a40981766d32fedc"
EXPECTED_PIPER_WHEEL_SHA256 = "3f60c1917de6d8e8033f395878ad3f88f6dfee88a8b05f98971a275f76a38484"
PIPER_PY = "myai-piper-venv/bin/python"
VARIANTS = (("normal", 1.0), ("slower", 1.25))
MAX_VOICE_BYTES = 70_000_000
MAX_SYNTH_WAV_BYTES = 350_000
MIN_DISK_SAFE = 4 * 1024**3

_PIPER_RENDER = r"""
import io,os,sys,wave
from piper import PiperVoice,SynthesisConfig
voice=PiperVoice.load(os.environ["MYAI_PINNED_PIPER_ALMA_MODEL"])
scale=float(os.environ["MYAI_PINNED_PIPER_LENGTH_SCALE"])
assert scale in (1.0,1.25)
buf=io.BytesIO()
with wave.open(buf,"wb") as sink:
    voice.synthesize_wav("Vad heter du?", sink,
        syn_config=SynthesisConfig(length_scale=scale))
data=buf.getvalue()
assert 44<=len(data)<=350000
sys.stdout.buffer.write(data)
"""

def _digest_file(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _download_verified_voice(destination: Path) -> bool:
    """Only fixed HF voice names on a fixed revision; download into temp."""
    if destination.exists() or destination.is_symlink():
        return False
    destination.mkdir(mode=0o700)
    voice = destination / VOICE_MODEL
    config = destination / VOICE_CONFIG
    try:
        for name, limit in ((VOICE_MODEL, MAX_VOICE_BYTES),
                            (VOICE_CONFIG, 14000)):
            target=destination / name
            url=HF_ROOT+PINNED_VOICE_REVISION+"/"+VOICE_SUBDIR+"/"+name
            with urlopen(url,timeout=35) as response, target.open("xb") as dst:
                received=0
                while True:
                    chunk=response.read(131072)
                    if not chunk:
                        break
                    received+=len(chunk)
                    if received>limit:
                        return False
                    dst.write(chunk)
        if not 55_000_000 < voice.stat().st_size < MAX_VOICE_BYTES:
            return False
        if _digest_file(voice)!=VOICE_WEIGHTS_SHA256:
            return False
        raw=config.read_bytes()
        if not 4000<=len(raw)<=14000:
            return False
        info=json.loads(raw)
        if not isinstance(info,dict):
            return False
        if (info.get("dataset")!="alma"
                or info.get("audio",{}).get("sample_rate")!=22050
                or info.get("language",{}).get("code")!="sv_SE"
                or info.get("espeak",{}).get("voice")!="sv"):
            return False
        return True
    except (OSError,ValueError,TypeError,TimeoutError):
        return False


def _render_once(root: Path, model: Path, scale: float) -> bytes | None:
    interpreter=root/PIPER_PY
    if not interpreter.is_file() or not model.is_file() or model.is_symlink():
        return None
    env=os.environ.copy()
    env.update({
        "MYAI_PINNED_PIPER_ALMA_MODEL":str(model),
        "MYAI_PINNED_PIPER_LENGTH_SCALE":str(scale),
        "PYTHONDONTWRITEBYTECODE":"1",
        "OMP_NUM_THREADS":"2",
        "OPENBLAS_NUM_THREADS":"1",
        "OMP_WAIT_POLICY":"PASSIVE",
    })
    def limit():
        resource.setrlimit(resource.RLIMIT_CPU,(100,100))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    try:
        p=subprocess.run(
            [str(interpreter),"-I","-c",_PIPER_RENDER],
            cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            check=False,timeout=120,preexec_fn=limit,
        )
    except (OSError,subprocess.TimeoutExpired):
        return None
    if p.returncode or not 44<=len(p.stdout)<=MAX_SYNTH_WAV_BYTES:
        return None
    return p.stdout


def compare_alma_swedish(root: Path, *, authorized: bool=False,
                         machine: str | None=None) -> dict[str,object]:
    out:dict[str,object]={
        "status":"not-authorized",
        "piper_voice_sha256_verified":False,
        "tiny_results":[], "base_results":[],
        "piper_variants_run":0,
        "real_microphone_opened":False, "speaker_opened":False,
        "user_audio_processed":False, "raw_transcript_logged":False,
        "wav_saved":False, "geniex_called":False,"ollama_called":False,
        "production_changed":False,
    }
    if not authorized:
        return out
    if (machine or platform.machine()).lower() not in ("aarch64","arm64"):
        out["status"]="blocked-architecture"
        return out
    scratch=os.environ.get("RUNNER_TEMP","")
    try:
        if (not scratch or root.is_symlink() or
                root.resolve(strict=True).parent!=Path(scratch).resolve(strict=True)
                or not root.name.startswith("myai-alma-compare-")):
            out["status"]="blocked-nonisolated-root"
            return out
    except (OSError,ValueError):
        out["status"]="blocked-nonisolated-root"
        return out
    if ((mem_available_kib() or 0)<MIN_MEM_AVAILABLE_KIB
            or (disk_free_bytes(root) or 0)<max(MIN_DISK_AVAILABLE_BYTES,MIN_DISK_SAFE)):
        out["status"]="blocked-resource-gate"
        return out
    stt_py=root/STT_PYTHON
    tiny=root/SMALL_FOLDER
    base=root/BASE_FOLDER
    if (not stt_py.is_file() or
            model_integrity(tiny).get("model_sha256")!=EXPECTED_MODEL_SHA256
            or base.exists() or base.is_symlink()):
        out["status"]="blocked-unverified-tiny-or-base-layout"
        return out
    voice_dir=root/"pinned-piper-alma"
    if not _download_verified_voice(voice_dir):
        out["status"]="pinned-alma-download-or-integrity-failed"
        return out
    out["piper_voice_sha256_verified"]=True
    piper_pcm=[]
    for label,scale in VARIANTS:
        data=_render_once(root,voice_dir/VOICE_MODEL,scale)
        if data is None:
            out["status"]="piper-tts-render-failed"
            return out
        pcm=wav_to_three_second_capture(data)
        del data
        if pcm is None or len(pcm)!=CAPTURE_BYTES:
            out["status"]="piper-rendered-capture-format-failed"
            return out
        signal=classify_pcm_quality(pcm)
        if signal not in ("bounded-audio-level","low-microphone-level",
                          "very-loud-microphone-level"):
            out["status"]="piper-rendered-signal-invalid"
            return out
        piper_pcm.append(pcm)
    joined=b"".join(piper_pcm)
    del piper_pcm
    out["piper_variants_run"]=2
    for name,weights in (("tiny",tiny),("base",base)):
        if (mem_available_kib() or 0)<MIN_FREED_RAM_KIB:
            out["status"]="blocked-inference-memory-gate"
            return out
        if name=="base":
            downloaded=_limited_child(stt_py,_DOWNLOAD_BASE,root)
            if (not downloaded["ok"]
                    or downloaded["payload"].get("downloaded") is not True
                    or not base_integrity(base)):
                out["status"]="pinned-base-download-or-integrity-failed"
                return out
        result=_limited_child(stt_py,_INFERENCE,root,model=weights,pcm=joined)
        if not result["ok"]:
            out["status"]=name+"-whisper-failed"
            return out
        payload=result["payload"]
        measurements=payload.get("measurements")
        if (payload.get("local_cpu_model_loaded") is not True
                or payload.get("mic_used") is not False
                or payload.get("speaker_used") is not False
                or not isinstance(measurements,list) or len(measurements)!=4):
            out["status"]="invalid-"+name+"-measurement"
            return out
        scrubbed=[]
        for i,item in enumerate(measurements):
            prox=item.get("proximity") if isinstance(item,dict) else None
            if (not isinstance(prox,dict)
                    or set(prox)!={"distance_band","word_count_band",
                         "target_words_present","target_words_aligned",
                         "target_words_in_order","exact_phrase_contained"}
                    or prox["distance_band"] not in ("0","1-2","3-5","6-10","11+")
                    or prox["word_count_band"] not in ("0","1-2","3","4-6","7+")
                    or type(prox["target_words_present"]) is not int
                    or not 0<=prox["target_words_present"]<=3
                    or type(prox["target_words_aligned"]) is not int
                    or not 0<=prox["target_words_aligned"]<=3
                    or type(prox["target_words_in_order"]) is not bool
                    or type(prox["exact_phrase_contained"]) is not bool
                    or item.get("beam")!=BEAMS[i%2]
                    or type(item.get("matched")) is not bool
                    or item.get("category") not in (
                        "approved","empty","short-unmatched","other-unmatched")
                    or type(item.get("seconds")) not in (int,float)
                    or not 0<=item["seconds"]<=MAX_INFERENCE_SECONDS):
                out["status"]="invalid-"+name+"-measurement"
                return out
            scrubbed.append({
                "piper_variant":VARIANTS[i//2][0],
                "beam":item["beam"],
                "matched":item["matched"],
                "category":item["category"],
                "distance_band":prox["distance_band"],
                "target_words_present":prox["target_words_present"],
                "target_words_aligned":prox["target_words_aligned"],
                "target_words_in_order":prox["target_words_in_order"],
            })
        out[name+"_results"]=scrubbed
        rss=payload.get("peak_rss_mib")
        if type(rss) in (int,float) and 0<=rss<=4096:
            out[name+"_rss_mib"]=rss
    out["status"]="pinned-piper-alma-whisper-comparison-complete"
    return out


def main() -> int:
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument("--runner-temp",type=Path,required=True)
    args.add_argument("--allow-synthetic-alma-only",action="store_true")
    parsed=args.parse_args()
    report=compare_alma_swedish(
        parsed.runner_temp,authorized=parsed.allow_synthetic_alma_only,
    )
    print("Pinned Swedish Piper Alma to Tiny/Base diagnosis:",
          json.dumps(report,sort_keys=True))
    return 0 if report["status"] in (
        "not-authorized","pinned-piper-alma-whisper-comparison-complete"
    ) else 2


if __name__=="__main__":
    raise SystemExit(main())
