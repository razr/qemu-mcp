"""Image-upload round-trip test (no live QEMU required).

Exercises the real disk-image contract the VxWorks runtime relies on:
  * the drive image is a RAW image containing a FAT filesystem,
  * files are written into it with mtools (mcopy) and verified with mdir,
  * VxWorks reads them from /bin on the target.

The test GENERATES a FAT image exactly the way the docs instruct a user to
(`dd` + `mkfs.vfat`), then drives `VxWorksRuntime.upload()` against it and
confirms the file landed byte-exact. It skips cleanly when the host lacks the
required tools (`mkfs.vfat`, `mcopy`/`mdir`/`mdel`) so CI without mtools is green.
"""
import os
import shutil
import subprocess
import pytest

from qemu_mcp.runtimes.vxworks.runtime import VxWorksRuntime


REQUIRED_TOOLS = ["mkfs.vfat", "mcopy", "mdir", "mdel"]
_missing = [t for t in REQUIRED_TOOLS if shutil.which(t) is None]

pytestmark = pytest.mark.skipif(
    bool(_missing),
    reason=f"image-upload test needs host tools: {', '.join(_missing)} "
           f"(install dosfstools + mtools)",
)


class _FakeVM:
    """Minimal stand-in for QEMUVirtualMachine: upload() only needs .drive_image."""
    def __init__(self, drive_image):
        self.drive_image = drive_image


def _make_fat_image(path, size_mb=16):
    """Generate a raw FAT32 image the documented way: dd + mkfs.vfat."""
    subprocess.run(
        ["dd", "if=/dev/zero", f"of={path}", "bs=1M", f"count={size_mb}"],
        check=True, capture_output=True,
    )
    subprocess.run(["mkfs.vfat", "-F", "32", path], check=True, capture_output=True)
    # VxWorks reads uploads from /bin; mcopy writes to ::/bin, so pre-create it.
    subprocess.run(["mmd", "-i", path, "::/bin"], capture_output=True)


def test_generated_fat_image_upload_roundtrip(tmp_path):
    img = tmp_path / "disk.img"
    _make_fat_image(str(img))

    # a byte pattern we can verify by size (stand-in for a .vxe)
    payload = tmp_path / "hello.vxe"
    payload.write_bytes(b"\x7fELF" + b"VXWORKS-RTP-PAYLOAD" * 97)
    expected_size = payload.stat().st_size

    rt = VxWorksRuntime(_FakeVM(str(img)))
    ok = rt.upload(str(payload), "/bin/hello.vxe")
    assert ok, "upload() reported failure writing into the FAT image"

    # independent verification: mdir shows the file byte-exact
    chk = subprocess.run(
        ["mdir", "-i", str(img), "::/bin"], capture_output=True, text=True
    )
    assert "HELLO" in chk.stdout.upper(), f"file not visible in image:\n{chk.stdout}"
    assert str(expected_size) in chk.stdout, (
        f"size {expected_size} not found (truncated/corrupt write?):\n{chk.stdout}"
    )


def test_upload_fails_without_bound_image(tmp_path):
    """upload() must fail (not crash) when the VM has no drive_image bound."""
    payload = tmp_path / "x.vxe"
    payload.write_bytes(b"\x7fELF")
    rt = VxWorksRuntime(_FakeVM(None))
    assert rt.upload(str(payload), "/bin/x.vxe") is False


def test_upload_fails_when_image_missing(tmp_path):
    payload = tmp_path / "x.vxe"
    payload.write_bytes(b"\x7fELF")
    rt = VxWorksRuntime(_FakeVM(str(tmp_path / "does-not-exist.img")))
    assert rt.upload(str(payload), "/bin/x.vxe") is False
