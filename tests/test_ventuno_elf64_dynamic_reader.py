"""Build tiny synthetic ELF section headers for parser tests. Never execute ELF."""
import struct

from scripts.ventuno_elf64_dynamic_reader import inspect_elf64_dynamic


def make_elf(sonames=("libQnnHtp.so", "libc.so.6"), *, corrupt=False):
    payload = bytearray(1408)
    payload[0:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", payload, 18, 183)  # ELF EM_AARCH64
    struct.pack_into("<Q", payload, 40, 1024) # 3 section headers
    struct.pack_into("<HH", payload, 58, 64, 3)
    strings = b"\x00"
    offsets = []
    for name in sonames:
        offsets.append(len(strings))
        strings += name.encode("ascii") + b"\0"
    payload[512:512 + len(strings)] = strings
    dynamic = b"".join(struct.pack("<qQ", 1, at) for at in offsets)
    dynamic += struct.pack("<qQ", 29, 0)
    dynamic += struct.pack("<qQ", 0, 0)
    payload[640:640 + len(dynamic)] = dynamic
    dynamic_link = 99 if corrupt else 2
    # Section 0 empty; section 1 .dynamic; section 2 .dynstr.
    struct.pack_into("<IIQQQQIIQQ", payload, 1024 + 64,
                     0, 6, 0, 0, 640, len(dynamic), dynamic_link, 0, 8, 16)
    struct.pack_into("<IIQQQQIIQQ", payload, 1024 + 128,
                     0, 3, 0, 0, 512, len(strings), 0, 0, 1, 1)
    return bytes(payload)


def test_parses_elf_dependencies_without_executing_it(tmp_path):
    path = tmp_path / "fake.elf"
    path.write_bytes(make_elf())
    output = inspect_elf64_dynamic(path)
    assert output["status"] == "static_elf64_aarch64_parsed"
    assert output["needed"] == ["libQnnHtp.so", "libc.so.6"]
    assert output["has_runpath"] is True


def test_rejects_bad_link_or_untrusted_library_name(tmp_path):
    target = tmp_path / "fake.elf"
    target.write_bytes(make_elf(corrupt=True))
    assert inspect_elf64_dynamic(target)["needed"] == []
    target.write_bytes(make_elf(("../../secret.so",)))
    assert inspect_elf64_dynamic(target)["status"] == "unreadable_or_unsupported"


def test_rejects_missing_truncated_wrong_arch_and_too_many_sonames(tmp_path):
    target = tmp_path / "fake.elf"
    assert inspect_elf64_dynamic(target)["needed"] == []
    target.write_bytes(b"NOT AN ELF")
    assert inspect_elf64_dynamic(target)["needed"] == []
    raw = bytearray(make_elf())
    raw[18:20] = b"\x3e\x00"  # x86_64
    target.write_bytes(raw)
    assert inspect_elf64_dynamic(target)["needed"] == []
    too_many = tuple(f"liba{i}.so" for i in range(70))
    target.write_bytes(make_elf(too_many))
    assert inspect_elf64_dynamic(target)["needed"] == []


def test_rejects_out_of_range_section_table(tmp_path):
    target = tmp_path / "fake.elf"
    raw = bytearray(make_elf())
    struct.pack_into("<Q", raw, 40, len(raw) + 10)
    target.write_bytes(raw)
    assert inspect_elf64_dynamic(target)["status"] == "unreadable_or_unsupported"
