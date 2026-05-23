import os
import logging
from typing import Dict, Any, List, Optional
from qemu.machine import QEMUMachine
from .detector import ArchDetector

logger = logging.getLogger("qemu_mcp.qemu")

class QEMUManager:
    """
    Pure QEMU Backend Layer.
    Agnostic to Guest OS internals (VxWorks/Zephyr). Focuses strictly on
    VM hardware, process lifecycle, and byte piping.
    """
    def __init__(self):
        self.vm: Optional[QEMUMachine] = None
        self.info: Optional[Dict[str, Any]] = None
        self.log_path = "/app/qemu_vms.log"

    def start(self, kernel_path: str, guest_append_args: Optional[str] = None, platform_qemu_args: Optional[List[str]] = None) -> str:
        """Launches the hypervisor instance based on automatically detected binary architecture."""
        if self.vm and self.vm.is_running():
            return "Error: QEMU instance is already active."

        try:
            # 1. Detect target binary architecture (ELF parsing)
            self.info = ArchDetector.get_info(kernel_path)
            qemu_bin = self.info["qemu_bin"]

            # 2. Initialize QEMUMachine base
            self.vm = QEMUMachine(qemu_bin)

            # 3. Formulate baseline hardware-level definitions
            args = [
                "-m", "1G",
                "-kernel", kernel_path,
                "-nographic",
                "-serial", f"file:{self.log_path}",  # Note: Consider socket pairing for live reading
            ]

            # 4. Inject OS-specific hypervisor configurations passed down from the runtime layer
            if platform_qemu_args:
                args.extend(platform_qemu_args)

            # 5. Inject guest boot arguments into the system append block
            if guest_append_args:
                args.extend(["-append", guest_append_args])

            self.vm.add_args(*args)

            # Keep stdin open for raw runtime command streaming
            self.vm._console_set = True

            # 6. Fire up hypervisor
            self.vm.launch()
            return f"Started {qemu_bin} for {self.info['arch']}. Hardware layer up."

        except Exception as e:
            self.vm = None
            logger.error(f"Hypervisor boot failure: {e}")
            return f"Launch failed: {str(e)}"

    def stop(self) -> str:
        """Terminates the QEMU target machine instantly via QMP/Process signal."""
        if not self.vm or not self.vm.is_running():
            return "QEMU is not running."

        self.vm.shutdown()
        self.vm = None
        return "QEMU stopped and cleaned up."

    def status(self) -> Dict[str, Any]:
        """Queries hardware-level status via QMP."""
        if not self.vm or not self.vm.is_running():
            return {"status": "STOPPED", "arch": None}

        try:
            res = self.vm.qmp("query-status")
            status = res.get("return", {}).get("status", "unknown")
            return {"status": status.upper(), "arch": self.info["arch"]}
        except Exception as e:
            return {"status": "RUNNING_QMP_ERROR", "arch": self.info["arch"], "error": str(e)}

    def send_raw_bytes(self, data: bytes) -> bool:
        """Pushes raw bytes into the serial execution line of the guest processor."""
        if self.vm and self.vm.is_running() and self.vm._process.stdin:
            try:
                self.vm._process.stdin.write(data)
                self.vm._process.stdin.flush()
                return True
            except IOError:
                return False
        return False

