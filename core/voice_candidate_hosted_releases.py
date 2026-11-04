"""Source-reviewed candidate model artifacts for HOSTED-ONLY ASR trials.

This is not a production trust root: a code reviewer must still approve
source/model provenance and licensing. No model is downloaded or executed
by importing this module. All refs and sha256s are immutable full pins.

The published model SHA256 bytes are independently checked after download.
Whisper binary sha is obtained from the exact locally compiled source.
The live voice factory does not import or enable these candidates.
"""
from dataclasses import dataclass
import re


_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class HostedModelRelease:
    profile: str
    family: str
    repository: str
    revision: str
    filename: str
    bytes: int
    sha256: str
    license: str
    native_source_revision: str

    def __post_init__(self):
        if (not _SHA40.fullmatch(self.revision)
                or not _SHA40.fullmatch(self.native_source_revision)
                or not _SHA64.fullmatch(self.sha256)
                or not 1_000_000 <= self.bytes <= 2_000_000_000
                or "/" in self.filename or ".." in self.filename):
            raise ValueError("Invalid hosted pinned STT release manifest")

    @property
    def url(self):
        """Explicitly version-locked public file; do NOT use /main/ URLs."""
        return ("https://huggingface.co/" + self.repository
                + "/resolve/" + self.revision + "/" + self.filename)


_RELEASES = {
    "canary-1b-v2-q8": HostedModelRelease(
        profile="canary-1b-v2-q8", family="canary",
        repository="handy-computer/canary-1b-v2-gguf",
        revision="58d13c2c0102229aad45f7e19a77ddc42b41dd9a",
        filename="canary-1b-v2-Q8_0.gguf",
        bytes=1144290016,
        sha256="224f83d1bc487b3303b495a7d6874912fdece93de19d1a04b550829c30a5d289",
        license="cc-by-4.0",
        native_source_revision="5700f127e38dd53c4735ea23ef743b4b538eacd4",
    ),
    "whisper-small-q5_1": HostedModelRelease(
        profile="whisper-small-q5_1", family="whisper",
        repository="ggerganov/whisper.cpp",
        revision="5359861c739e955e79d9a303bcbc70fb988958b1",
        filename="ggml-small-q5_1.bin",
        bytes=190085487,
        sha256="ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb",
        license="mit",
        native_source_revision="4da27c41cebadb3cbbcd2563e9c7cbc8d84bdcad",
    ),
    "whisper-large-v3-turbo": HostedModelRelease(
        profile="whisper-large-v3-turbo", family="whisper",
        repository="ggerganov/whisper.cpp",
        revision="5359861c739e955e79d9a303bcbc70fb988958b1",
        filename="ggml-large-v3-turbo.bin",
        bytes=1624555275,
        sha256="1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69",
        license="mit",
        native_source_revision="4da27c41cebadb3cbbcd2563e9c7cbc8d84bdcad",
    ),
}


def hosted_model_release(profile):
    """Fail closed on all unknown profiles; this is not a user URL builder."""
    if type(profile) is not str or profile not in _RELEASES:
        raise ValueError("Unknown hosted-only pinned model profile")
    return _RELEASES[profile]
