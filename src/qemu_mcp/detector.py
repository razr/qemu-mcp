import os
from elftools.elf.elffile import ELFFile

class ArchDetector:
    # Map pyelftools machine strings to QEMU binary suffixes
    # pyelftools machine names are standard (e.g., 'x64', 'AArch64')
    MACHINE_TO_QEMU = {
        'x64': 'x86_64',
        'x86': 'i386',
        'AArch64': 'aarch64',
        'ARM': 'arm',
        'PowerPC': 'ppc'
    }

    @classmethod
    def get_info(cls, kernel_path: str):
        """Uses pyelftools to accurately detect kernel architecture."""
        if not os.path.exists(kernel_path):
            raise FileNotFoundError(f"Kernel not found at: {kernel_path}")

        with open(kernel_path, 'rb') as f:
            try:
                elffile = ELFFile(f)
                header = elffile.header
                
                # Get the human-readable machine name (e.g., 'x64')
                raw_arch = elffile.get_machine_arch()
                qemu_suffix = cls.MACHINE_TO_QEMU.get(raw_arch, "unknown")

                if qemu_suffix == "unknown":
                    raise ValueError(f"QEMU does not support arch: {raw_arch}")

                return {
                    "arch": qemu_suffix,
                    "qemu_bin": f"qemu-system-{qemu_suffix}",
                    "bitness": header['e_ident']['EI_CLASS'].replace('ELFCLASS', ''),
                    "endian": "little" if header['e_ident']['EI_DATA'] == 'ELFDATA2LSB' else "big"
                }
            except Exception as e:
                raise ValueError(f"Failed to parse ELF: {str(e)}")

# Example usage for the MCP Manager:
# info = ArchDetector.get_info("vxWorks")
# print(f"Detected: {info['qemu_bin']}") 

