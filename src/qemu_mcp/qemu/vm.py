# src/qemu_mcp/qemu/vm.py
import os
import subprocess
import logging
import time
from typing import List, Optional, Dict, Any

from .profile import QEMUProfile
from .console import QEMUConsole
from .monitor import QEMUMonitor  # Import your new class

logger = logging.getLogger("qemu_mcp.qemu")

class QEMUVirtualMachine:
    """
    Agnostic QEMU Hypervisor Instance.
    Drives the process directly via subprocess to guarantee exact parameter configurations
    while preserving native QMP monitoring via structured QEMUMonitor connections.
    """
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self.console: Optional[QEMUConsole] = None
        self.profile: Optional[QEMUProfile] = None
        self.host_target = os.getenv("MCP_QEMU_HOST", "127.0.0.1")
        self.monitor = QEMUMonitor(host=self.host_target, port=15556)
        self.log_path = "qemu_vms.log"
        self.args: List[str] = []
        self.binary: str = ""

    def start(self, kernel_path: str, profile_name: str = "vxworks_x86_64_default", extra_args: Optional[str] = None) -> bool:
        # Check if QEMU is already running in the background via port/QMP probe before starting a new one
        if self.monitor.connect(retries=1):
            logger.info("Target QEMU instance is already active in the background. Re-attaching.")
            self.monitor.disconnect()
            return True

        try:
            self.profile = QEMUProfile(log_path=self.log_path, profile_name=profile_name)
            qemu_bin = self.profile.qemu_bin

            args: List[str] = [
                qemu_bin,
                "-kernel", kernel_path,
                "-m", "1G",
                "-display", "none"
            ]

            boot_append = self.profile.append_args()
            if boot_append:
                args.extend(["-append", f'"{boot_append}"'])

            args.extend(self.profile.platform_args())
            args.extend(self.profile.network_args())

            args.extend([
                # Adding ,server=on,wait=off tells QEMU to wait for connections without dying on disconnect
                "-chardev", f"socket,id=console,host={self.host_target},port=15555,server=on,wait=off",
                "-serial", "chardev:console",

                "-chardev", f"socket,id=monitor,host={self.host_target},port=15556,server=on,wait=off",
                "-mon", "chardev=monitor,mode=control"
            ])

            if extra_args:
                args.extend(extra_args.split())

            self.args = args[1:]
            self.binary = qemu_bin

            # Launch completely detached from Python's process tree lifecycle hooks
            self._process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            # Write the PID to a file so other stateless instances can find it if needed
            with open("/tmp/qemu_mcp.pid", "w") as f:
                f.write(str(self._process.pid))

            time.sleep(0.5)
            self.monitor.connect()
            return True

        except Exception as e:
            self.stop()
            logger.error(f"Hypervisor startup exception encountered: {e}")
            raise e

    def stop(self, binary_name: Optional[str] = None) -> bool:
        """Safely shuts down the VM instance and releases process tree contexts."""
        # 1. Ask QEMU nicely via the monitor protocol first
        res = self.monitor.execute("quit")
        self.monitor.disconnect()

        # 2. Hard kill process fallback using profile variables if QMP failed or context was lost
        if "error" in res or (self._process and self._process.poll() is None):
            try:
                import signal

                # Resolve the exact executable name (e.g. "qemu-system-x86_64")
                qemu_bin_name = binary_name or (os.path.basename(self.binary) if self.binary else "qemu-system-x86_64")

                # CRITICAL FIX: Remove the "-f" flag from pgrep.
                # This matches ONLY the exact process name, ignoring the pytest argument string!
                pid_bytes = subprocess.check_output(["pgrep", "-x", qemu_bin_name])
                pids = pid_bytes.decode().strip().split()

                for pid_str in pids:
                    pid = int(pid_str)
                    if pid != os.getpid():
                        os.kill(pid, signal.SIGKILL)
            except Exception:
                if self._process:
                    self._process.kill()

        self._process = None
        self.console = None
        self.profile = None
        return True

    def status(self) -> Dict[str, Any]:
        """Queries the real hardware status straight via our explicit local QMP socket stream."""
        res = self.monitor.execute("query-status")

        if "error" in res:
            return {"status": "STOPPED", "arch": None}

        qmp_status = res.get("return", {}).get("status", "unknown")
        return {
            "status": qmp_status.upper(),
            "arch": self.profile.arch if self.profile else "X86_64"
        }

