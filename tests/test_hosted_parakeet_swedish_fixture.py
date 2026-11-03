"""Synthetic archive safety tests; no model downloads or microphone."""
import io
import tarfile

import pytest

from scripts.hosted_parakeet_swedish_fixture import (
    MODEL_DIR_NAME, EXPECTED_FILES, extract_required_files, verify_archive, public_pcm_vad_segments,
)


def write_archive(path, members=None):
    members = members if members is not None else list(EXPECTED_FILES)
    with tarfile.open(path, "w:bz2") as bundle:
        for name in members:
            payload = b"synthetic-model-data"
            item = tarfile.TarInfo(MODEL_DIR_NAME + "/" + name)
            item.size = len(payload)
            bundle.addfile(item, io.BytesIO(payload))


def test_only_exact_required_four_members_are_extracted(tmp_path):
    archive = tmp_path / "model.tar.bz2"
    write_archive(archive)
    result = extract_required_files(archive, tmp_path / "model")
    assert {p.name for p in result.iterdir()} == set(EXPECTED_FILES)
    for name in EXPECTED_FILES:
        assert (result / name).read_bytes() == b"synthetic-model-data"
    assert not verify_archive(archive)


def test_incomplete_archive_fails_closed(tmp_path):
    archive = tmp_path / "model.tar.bz2"
    write_archive(archive, ["encoder.int8.onnx"])
    with pytest.raises(ValueError, match="missing required"):
        extract_required_files(archive, tmp_path / "model")


def test_duplicate_member_fails_closed(tmp_path):
    archive = tmp_path / "model.tar.bz2"
    write_archive(archive, list(EXPECTED_FILES) + ["tokens.txt"])
    with pytest.raises(ValueError, match="Unexpected"):
        extract_required_files(archive, tmp_path / "model")


def test_linked_model_file_fails_closed(tmp_path):
    archive = tmp_path / "model.tar.bz2"
    with tarfile.open(archive, "w:bz2") as bundle:
        entry = tarfile.TarInfo(MODEL_DIR_NAME + "/encoder.int8.onnx")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "../../unsafe"
        bundle.addfile(entry)
    with pytest.raises(ValueError, match="Unexpected"):
        extract_required_files(archive, tmp_path / "model")


def test_existing_destination_rejected(tmp_path):
    archive = tmp_path / "model.tar.bz2"
    write_archive(archive)
    dest = tmp_path / "model"
    dest.mkdir()
    with pytest.raises(ValueError, match="Invalid destination"):
        extract_required_files(archive, dest)


def test_wrong_size_and_symlink_archive_rejected(tmp_path):
    fake = tmp_path / "fake.tar.bz2"
    fake.write_bytes(b"not-a-real-model")
    assert not verify_archive(fake)
    link = tmp_path / "link.tar.bz2"
    link.symlink_to(fake)
    assert not verify_archive(link)


def test_public_swedish_vad_last_frame_zero_padding_is_exact(tmp_path, monkeypatch):
    from modules.voice import sherpa_silero_segments as sm
    monkeypatch.setattr(
        "scripts.hosted_parakeet_swedish_fixture.verified_silero_model",
        lambda _: True,
    )
    observed = []
    class FakeSegmenter:
        def __init__(self, model_path, context_padding_ms=300):
            assert model_path and context_padding_ms == 300
        def feed(self, frame):
            observed.append(frame)
            return []
        def flush(self):
            return []
    monkeypatch.setattr(sm, "SherpaSileroSegments", FakeSegmenter)
    input_pcm = bytes([1, 0]) * 328  # 656 bytes; one full frame + 16-byte tail
    assert public_pcm_vad_segments(input_pcm, tmp_path / "fake.onnx") == []
    assert [len(x) for x in observed] == [640, 640]
    assert observed[0] == input_pcm[:640]
    assert observed[1][:16] == input_pcm[640:]
    assert observed[1][16:] == bytes(624)
