"""Pinned public STT model release artifacts for the isolated hosted ARM64 trial.

The two exact model bytes/size values are pinned to upstream public model
release metadata. They are NOT an installation manifest for VENTUNO. No
download, network, subprocess or native inference occurs on import.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class PinnedModelArtifact:
    profile: str
    repository: str
    revision: str
    filename: str
    sha256: str
    byte_size: int
    license: str

    def validate(self):
        if (not re.fullmatch(r"[a-z0-9-]+/[a-zA-Z0-9_.-]+", self.repository)
                or not re.fullmatch(r"[0-9a-f]{40}", self.revision)
                or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)
                or not re.fullmatch(r"[a-zA-Z0-9_.-]+", self.filename)
                or not 10**8 <= self.byte_size <= 2 * 10**9
                or self.license not in ("cc-by-4.0", "mit")):
            raise ValueError("Untrusted hosted model manifest")
        if self.profile not in ("canary-1b-v2-q8", "whisper-large-v3-turbo"):
            raise ValueError("Unsupported model profile")
        return self

    @property
    def url(self):
        self.validate()
        return (
            f"https://huggingface.co/{self.repository}/resolve/"
            f"{self.revision}/{self.filename}"
        )


PINNED_CANARY = PinnedModelArtifact(
    profile="canary-1b-v2-q8",
    repository="handy-computer/canary-1b-v2-gguf",
    revision="58d13c2c0102229aad45f7e19a77ddc42b41dd9a",
    filename="canary-1b-v2-Q8_0.gguf",
    sha256="224f83d1bc487b3303b495a7d6874912fdece93de19d1a04b550829c30a5d289",
    byte_size=1144290016,
    license="cc-by-4.0",
)

PINNED_WHISPER = PinnedModelArtifact(
    profile="whisper-large-v3-turbo",
    repository="ggerganov/whisper.cpp",
    revision="5359861c739e955e79d9a303bcbc70fb988958b1",
    filename="ggml-large-v3-turbo.bin",
    sha256="1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69",
    byte_size=1624555275,
    license="mit",
)

HOSTED_ARTIFACTS = (PINNED_CANARY, PINNED_WHISPER)


def validate_hosted_manifest():
    """Refuse a missing/duplicate model family; never silently downgrade."""
    if ({m.profile for m in HOSTED_ARTIFACTS}
            != {"canary-1b-v2-q8", "whisper-large-v3-turbo"}
            or len(HOSTED_ARTIFACTS) != 2):
        raise ValueError("Incomplete independent hosted model manifest")
    return tuple(artifact.validate() for artifact in HOSTED_ARTIFACTS)
