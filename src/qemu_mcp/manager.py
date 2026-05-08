import os
from qemu.machine import QEMUMachine
from .detector import ArchDetector

class QEMUManager:
    def __init__(self):
        self.vm = None
        self.info = None

    def start(self, kernel_path: str, extra_args: str = None):
        """Detects arch and launches VxWorks via QEMUMachine."""
        if self.vm and self.vm.is_running():
            return "Error: QEMU is already running."

        try:
            # 1. Use pyelftools-based detector
            self.info = ArchDetector.get_info(kernel_path)
            qemu_bin = self.info["qemu_bin"]

            # 2. Initialize QEMUMachine
            # It automatically manages QMP sockets and process cleanup
            self.vm = QEMUMachine(qemu_bin)

            # 3. Build the VxWorks-specific bootline
            # Standard for SR0120/26.03 (FTP/Network enabled)
            bootline = (
                "bootline: gei(0,0)host:vxWorks h=10.0.2.2 e=10.0.2.15 "
                "u=target pw=vxTarget o=gei0"
            )

            self.log_path = "/app/qemu_vms.log"

            # 4. Configure Arguments
            args = [
                "-m", "1G",
                "-kernel", kernel_path,
                "-nographic",
                "-serial", f"file:{self.log_path}",
                "-append", bootline,
                "-net", "nic,model=e1000" if self.info["arch"] == "x86_64" else "nic",
                "-net", "user,hostfwd=tcp::2121-:21,hostfwd=tcp::1534-:1534"
            ]
            
            if extra_args:
                args.extend(extra_args.split())

            self.vm.add_args(*args)

            # 5. Launch
            self.vm.launch()
            return f"Started {qemu_bin} for {self.info['arch']}. QMP active."

        except Exception as e:
            self.vm = None
            return f"Launch failed: {str(e)}"

    def stop(self):
        """Safely shuts down the VM and cleans up resources."""
        if not self.vm or not self.vm.is_running():
            return "QEMU is not running."
        
        self.vm.shutdown()
        self.vm = None
        return "QEMU stopped and cleaned up."

    def status(self):
        """Queries QMP for the real-time CPU status."""
        if not self.vm or not self.vm.is_running():
            return "Status: STOPPED"

        try:
            res = self.vm.qmp("query-status")
            status = res.get("return", {}).get("status", "unknown")
            return f"Status: {status.upper()} (Arch: {self.info['arch']})"
        except Exception as e:
            return f"Status: RUNNING (QMP Error: {str(e)})"

