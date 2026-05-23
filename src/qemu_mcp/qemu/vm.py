# src/qemu_mcp/qemu/vm.py
import os
import logging
from typing import List, Optional, Dict, Any
from qemu.machine import QEMUMachine
from .profile import QEMUProfile
from .console import QEMUConsole

logger = logging.getLogger("qemu_mcp.qemu")

class QEMUVirtualMachine:
    def __init__(self):
        self.machine: Optional[QEMUMachine] = None
        self.console: Optional[QEMUConsole] = None
        self.profile: Optional[QEMUProfile] = None
        self.log_path = "qemu_vms.log"

    def start(self, kernel_path: str, profile_name: str = "vxworks_x86_64_default", extra_args: Optional[str] = None) -> bool:
        if self.machine and self.machine.is_running():
            return False

        try:
            self.profile = QEMUProfile(log_path=self.log_path, profile_name=profile_name)
            qemu_bin = self.profile.qemu_bin
            
            # Initialize clean instance
            self.machine = QEMUMachine(qemu_bin)

            # 1. Build the COMPLETE command line explicitly via add_args
            args: List[str] = [
                "-kernel", kernel_path,
                "-m", "1G",
                "-monitor", "none",
                "-display", "none"
            ]

            boot_append = self.profile.append_args()
            if boot_append:
                args.extend(["-append", f'"{boot_append}"'])

            args.extend(self.profile.platform_args())
            args.extend(self.profile.network_args())

            # 2. Configure a predictable, un-hidden TCP socket loop for your interactive serial line
            # This completely replaces the broken internal '_console_set' behavior
            args.extend([
                "-chardev", "socket,id=console,host=127.0.0.1,port=15555,server=on,wait=off",
                "-serial", "chardev:console"
            ])

            if extra_args:
                args.extend(extra_args.split())

            # Push everything down the public args vector
            self.machine.add_args(*args)
            self.machine._console_set = False

            # 3. Fire up the execution engine (Keep internal console interception OFF)
            self.machine.launch()
            
            # Instantiate our non-blocking socket interface tracker
            self.console = QEMUConsole(self)
            self.console._connect_socket()
            return True

        except Exception as e:
            self.machine = None
            self.profile = None
            logger.error(f"Hypervisor startup exception encountered: {e}")
            raise e

    def stop(self) -> bool:
        if not self.machine or not self.machine.is_running():
            return False
        self.machine.shutdown()
        self.machine = None
        self.console = None
        self.profile = None
        return True

    def status(self) -> Dict[str, Any]:
        if not self.machine or not self.machine.is_running():
            return {"status": "STOPPED", "arch": None}
        try:
            res = self.machine.qmp("query-status")
            qmp_status = res.get("return", {}).get("status", "unknown")
            return {"status": qmp_status.upper(), "arch": self.profile.arch if self.profile else None}
        except Exception as e:
            return {"status": "RUNNING_QMP_ERROR", "arch": self.profile.arch if self.profile else None, "error": str(e)}

