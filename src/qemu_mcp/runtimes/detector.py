# src/qemu_mcp/runtimes/detector.py
import os
from typing import Dict, Any
from elftools.elf.elffile import ELFFile

# Kept strictly to modern 64-bit QEMU execution targets
MACHINE_TO_QEMU = {
    'x64': 'x86_64',
    'AArch64': 'aarch64'
}

def get_arch_info(kernel_path: str) -> Dict[str, Any]:
    """
    Pure module function focused strictly on modern 64-bit kernel configurations.
    """
    if not os.path.exists(kernel_path):
        raise FileNotFoundError(f"Kernel image file not found at: {kernel_path}")

    with open(kernel_path, 'rb') as f:
        try:
            elffile = ELFFile(f)

            raw_arch = elffile.get_machine_arch()
            qemu_suffix = MACHINE_TO_QEMU.get(raw_arch, "unknown")

            if qemu_suffix == "unknown":
                raise ValueError(f"QEMU layer does not support architecture: {raw_arch}")

            return {
                "arch": qemu_suffix,
                "qemu_bin": f"qemu-system-{qemu_suffix}"
            }
        except Exception as e:
            raise ValueError(f"Failed to parse ELF hardware headers: {str(e)}")

