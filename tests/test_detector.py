"""Arch-detection tests for runtimes/detector.get_arch_info (no real kernel needed).

Synthesizes minimal 64-bit ELF headers (just enough for pyelftools to read
e_machine) for x86_64 (EM_X86_64=62) and aarch64 (EM_AARCH64=183), and checks the
machine->qemu-arch mapping plus the error paths (missing file, non-ELF).
"""
import struct
import pytest

from qemu_mcp.runtimes.detector import get_arch_info


def _elf64_header(e_machine: int) -> bytes:
    """Build a minimal valid 64-bit little-endian ELF header with the given machine."""
    e_ident = (
        b"\x7fELF"      # magic
        b"\x02"          # EI_CLASS = ELFCLASS64
        b"\x01"          # EI_DATA  = ELFDATA2LSB (little endian)
        b"\x01"          # EI_VERSION
        b"\x00"          # EI_OSABI
        + b"\x00" * 8    # EI_PAD
    )
    # e_type(2) e_machine(2) e_version(4) e_entry(8) e_phoff(8) e_shoff(8)
    # e_flags(4) e_ehsize(2) e_phentsize(2) e_phnum(2) e_shentsize(2)
    # e_shnum(2) e_shstrndx(2)
    rest = struct.pack(
        "<HHIQQQIHHHHHH",
        2,            # e_type = ET_EXEC
        e_machine,    # e_machine
        1,            # e_version
        0, 0, 0,      # entry, phoff, shoff
        0,            # flags
        64,           # ehsize
        0, 0,         # phentsize, phnum
        0, 0,         # shentsize, shnum
        0,            # shstrndx
    )
    return e_ident + rest


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_detects_x86_64(tmp_path):
    k = _write(tmp_path, "vxWorks.x86", _elf64_header(62))  # EM_X86_64
    info = get_arch_info(k)
    assert info["arch"] == "x86_64"
    assert info["qemu_bin"] == "qemu-system-x86_64"


def test_detects_aarch64(tmp_path):
    k = _write(tmp_path, "vxWorks.arm", _elf64_header(183))  # EM_AARCH64
    info = get_arch_info(k)
    assert info["arch"] == "aarch64"
    assert info["qemu_bin"] == "qemu-system-aarch64"


def test_unsupported_machine_raises(tmp_path):
    # EM_RISCV = 243 — not in the modern-64-bit QEMU map
    k = _write(tmp_path, "vxWorks.rv", _elf64_header(243))
    with pytest.raises(ValueError):
        get_arch_info(k)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_arch_info(str(tmp_path / "nope"))


def test_non_elf_raises(tmp_path):
    k = _write(tmp_path, "notelf", b"this is not an ELF file")
    with pytest.raises(ValueError):
        get_arch_info(k)
