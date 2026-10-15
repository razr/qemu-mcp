# tests/test_vxworks_runtime.py
"""Unit tests for the VxWorks runtime that need no live QEMU:
EDR fault-record parsing, outcome classification regexes, and the disk profile.
"""
import pytest
from qemu_mcp.qemu.profile import QEMUProfile, PROFILES
from qemu_mcp.runtimes.vxworks.runtime import (
    VxWorksRuntime, LAUNCHED_RE, SIGNAL_RE, INSTANTIATE_FAIL,
)


def test_disk_profile_builds_expected_args():
    p = QEMUProfile("x.log", "vxworks_x86_64_disk")
    assert p.memory == "2G"
    assert p.platform_args() == ["-machine", "q35", "-cpu", "Nehalem"]
    drive = p.drive_args("/data/vx.img")
    assert "file=/data/vx.img,if=none,id=vxdisk,format=raw" in drive
    assert "ich9-ahci,id=ahci" in drive
    assert "ide-hd,drive=vxdisk,bus=ahci.0" in drive
    assert "Done executing startup script" in p.boot_ready_markers()
    assert p.command_shell_prompt == "[vxWorks"
    assert p.kernel_shell_prompt == "->"


def test_disk_profile_requires_image():
    p = QEMUProfile("x.log", "vxworks_x86_64_disk")
    with pytest.raises(ValueError):
        p.drive_args(None)


def test_diskless_profile_has_no_drive():
    p = QEMUProfile("x.log", "vxworks_x86_64_default")
    assert p.drive_args(None) == []


def test_launch_regex():
    line = "Process '/usr/bin/iprobe' (process Id = 0xffff8000187a0000) launched."
    m = LAUNCHED_RE.search(line)
    assert m and m.group(1) == "0xffff8000187a0000"


def test_signal_regex():
    line = "0xffff8000187ae000 (iIprobe): RTP 0xffff8000187a0000 has been deleted due to signal 11."
    m = SIGNAL_RE.search(line)
    assert m and m.group(1) == "11"


def test_edr_parse_pc_and_access():
    raw = (
        "Exception: Page Fault\n"
        "Program Counter: 0x00000000deadbeef\n"
        "Access Address: 0x0000000000000000\n"
        "Task: iIprobe\n"
    )
    out = VxWorksRuntime._parse_edr(raw)
    assert out["pc"] == "0x00000000deadbeef"
    assert out["access_address"] == "0x0000000000000000"
    assert out["exception"].startswith("Page Fault")
    assert out["task"] == "iIprobe"
    assert out["has_record"] is True


def test_edr_parse_no_record():
    out = VxWorksRuntime._parse_edr("-> \nvalue = 0 = 0x0\n")
    assert out["pc"] is None
    assert out["access_address"] is None
    assert out["has_record"] is False


def test_edr_parse_register_dump_null_pc():
    """Real on-target format: register dump with lowercase 'pc = 0x0' + Traceback."""
    raw = (
        "rsp        = 0x0000000000437f48   r14        = 0x0000000000438ca8\r\n"
        "rbp        = 0x0000000000438c90   r15        = 0x0000000000000001\r\n"
        "pc         = 0x0000000000000000   eflags     = 0x0000000000000282\r\n"
        "tlsbase    = 0x0000000000488180\r\n\r\n<<<<<Traceback>>>>>\r\n"
    )
    out = VxWorksRuntime._parse_edr(raw)
    assert out["pc"] == "0x0000000000000000"
    assert out["has_record"] is True
    assert out["registers"].get("rsp") == "0x0000000000437f48"
    assert out["registers"].get("pc") == "0x0000000000000000"
    assert "NULL" in (out["classification"] or "")
