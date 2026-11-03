"""Optional hosted-only SHA256-pinned Whisper large-v3 Turbo Q5 experiment.

No production registration, audio, network, model import or download here.
Q5 is the *same* Whisper family as F16 and never becomes a third
independent STT vote beside another Whisper quantization.

HF model byte size was only exposed as a rounded 574 MB by the public
release page, so the bounded download uses a conservative accepted size
interval PLUS an exact published SHA256 rather than inventing exact bytes.
"""
import hashlib
from pathlib import Path
import re


PROFILE = "whisper-large-v3-turbo-q5"
REPOSITORY = "ggerganov/whisper.cpp"
REVISION = "5359861c739e955e79d9a303bcbc70fb988958b1"
FILENAME = "ggml-large-v3-turbo-q5_0.bin"
SHA256 = "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2"
# Conservative range; exact sha256, not approximate size, is the identity.
MIN_BYTES = 500_000_000
MAX_BYTES = 650_000_000
LICENSE = "mit"


def quantized_release_url():
    if (not re.fullmatch(r"[0-9a-f]{40}", REVISION)
            or not re.fullmatch(r"[0-9a-f]{64}", SHA256)
            or PROFILE != "whisper-large-v3-turbo-q5"
            or FILENAME != "ggml-large-v3-turbo-q5_0.bin"):
        raise ValueError("Untrusted Whisper Q5 trial release")
    return f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{FILENAME}"


def verify_quantized_file(path):
    """Fail closed on wrong/partial files, symlinks or mismatching bytes."""
    quantized_release_url()
    p = Path(path)
    if not p.is_file() or p.is_symlink() or p.name != FILENAME:
        raise ValueError("Untrusted Whisper Q5 model file")
    if not MIN_BYTES <= p.stat().st_size <= MAX_BYTES:
        raise ValueError("Unexpected Whisper Q5 model length")
    digest = hashlib.sha256()
    with p.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError("Whisper Q5 model checksum mismatch")
    return True
