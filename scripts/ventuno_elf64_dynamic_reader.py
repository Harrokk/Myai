"""Bounded static ELF64/AArch64 DT_NEEDED reader (pure Python, no execution).

Reads only ELF header, section headers, dynamic section and linked string
table. No dlopen, ELF loader, readelf, subprocess, model or drivers invoked.
Rejects unsupported/oversized/malformed ELF and never prints file paths.
"""

import os
from pathlib import Path
import re
import stat
import struct

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_SECTIONS = 512
MAX_STRING_BYTES = 1024 * 1024
MAX_DYNAMIC_BYTES = 32 * 1024
MAX_NEEDED = 64
NAME = re.compile(r"^[A-Za-z0-9_.+-]{1,100}\.so(?:\.[0-9.]+)?$")


def _read_at(fd, start, amount, file_size):
    if start < 0 or amount < 0 or start > file_size or amount > file_size - start:
        raise ValueError("out-of-range-ELF-section")
    fd.seek(start)
    result = fd.read(amount)
    if len(result) != amount:
        raise ValueError("incomplete-ELF-data")
    return result


def inspect_elf64_dynamic(path):
    """Return validated linked sonames; no attempt to resolve loader search."""
    empty = {"status": "unreadable_or_unsupported", "needed": [],
             "has_runpath": False}
    try:
        with Path(path).open("rb") as fd:
            meta = os.fstat(fd.fileno())
            if (not stat.S_ISREG(meta.st_mode)
                    or not 64 <= meta.st_size <= MAX_FILE_BYTES):
                return empty
            header = _read_at(fd, 0, 64, meta.st_size)
            if (header[:4] != b"\x7fELF" or header[4:6] != b"\x02\x01"
                    or struct.unpack_from("<H", header, 18)[0] != 183):
                return empty
            shoff = struct.unpack_from("<Q", header, 40)[0]
            shentsize, shnum = struct.unpack_from("<HH", header, 58)
            if (shentsize != 64 or not 1 <= shnum <= MAX_SECTIONS
                    or shoff == 0):
                return empty
            block = _read_at(fd, shoff, shnum * shentsize, meta.st_size)
            sections = [
                struct.unpack_from("<IIQQQQIIQQ", block, index * 64)
                for index in range(shnum)
            ]
            dynamic = [x for x in sections if x[1] == 6]
            if len(dynamic) != 1:
                return empty
            section = dynamic[0]
            _, _, _, _, dynamic_offset, dynamic_size, link, _, _, entsize = section
            if not 0 < dynamic_size <= MAX_DYNAMIC_BYTES or entsize != 16:
                return empty
            if link >= len(sections) or sections[link][1] != 3:
                return empty
            str_section = sections[link]
            str_offset, str_size = str_section[4], str_section[5]
            if not 0 < str_size <= MAX_STRING_BYTES:
                return empty
            dynamic_bytes = _read_at(fd, dynamic_offset, dynamic_size, meta.st_size)
            strings = _read_at(fd, str_offset, str_size, meta.st_size)
            needed = []
            runpath = False
            for cursor in range(0, len(dynamic_bytes) - 15, 16):
                tag, value = struct.unpack_from("<qQ", dynamic_bytes, cursor)
                if tag == 0:
                    break
                if tag in (15, 29):
                    runpath = True
                if tag != 1:
                    continue
                if value >= len(strings):
                    return empty
                end = strings.find(b"\0", value)
                if end < 0 or end - value > 100:
                    return empty
                try:
                    name = strings[value:end].decode("ascii")
                except UnicodeError:
                    return empty
                if not NAME.fullmatch(name):
                    return empty
                if name not in needed:
                    needed.append(name)
                if len(needed) > MAX_NEEDED:
                    return empty
            return {
                "status": "static_elf64_aarch64_parsed",
                "needed": needed, "has_runpath": runpath,
            }
    except (OSError, ValueError, OverflowError, struct.error, TypeError):
        return empty
