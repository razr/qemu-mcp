# src/qemu_mcp/qemu/vm.py
import os
import subprocess
import logging
import socket
import json
import time
from typing import List, Optional, Dict, Any
from .profile import QEMUProfile
from .console import QEMUConsole

logger = logging.getLogger("qemu_mcp.qemu")

class QEMUVirtualMachine:
    """
    Agnostic QEMU Hypervisor Instance.
    Drives the process directly via subprocess to guarantee exact parameter configurations
    while preserving native QMP monitoring via raw Python sockets.
    """
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self.console: Optional[QEMUConsole] = None
        self.profile: Optional[QEMUProfile] = None
        self.qmp_sock: Optional[socket.socket] = None
        self.log_path = "qemu_vms.log"
        self.args: List[str] = []
        self.binary: str = ""

    def start(self, kernel_path: str, profile_name: str = "vxworks_x86_64_default", extra_args: Optional[str] = None) -> bool:
        if self._process and self._process.poll() is None:
            logger.warning("Start requested, but target QEMU instance is already active.")
            return False

        try:
            self.profile = QEMUProfile(log_path=self.log_path, profile_name=profile_name)
            qemu_bin = self.profile.qemu_bin

            # 1. Assemble your exact validated parameters explicitly
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

            # 2. Configure BOTH the Console and the QMP Monitor explicitly via TCP sockets
            args.extend([
                # Serial Console Interface (Port 15555)
                "-chardev", "socket,id=console,host=127.0.0.1,port=15555,server=on,wait=off",
                "-serial", "chardev:console",

                # QMP Monitor Interface (Port 15556)
                "-chardev", "socket,id=monitor,host=127.0.0.1,port=15556,server=on,wait=off",
                "-mon", "chardev=monitor,mode=control"
            ])

            if extra_args:
                args.extend(extra_args.split())

            # Expose properties to the test framework tracking layer
            self.args = args[1:]
            self.binary = qemu_bin

            # 3. Launch the hypervisor process directly via OS system hooks
            self._process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Creates a process group for clean resource termination
            )

            # 4. Instantiate and immediately connect the non-blocking interfaces
            self.console = QEMUConsole(self)
            self.console._connect_socket()

            # Connect to our freshly exposed QMP server socket loop
            self._connect_qmp()

            return True

        except Exception as e:
            self.stop()
            logger.error(f"Hypervisor startup exception encountered: {e}")
            raise e

    def _connect_qmp(self):
        """Establishes connection to the QEMU QMP socket server and runs the handshake."""
        try:
            self.qmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.qmp_sock.settimeout(1.0)

            # Poll loop to wait for QEMU's server port to spin up
            for _ in range(5):
                try:
                    self.qmp_sock.connect(("127.0.0.1", 15556))
                    break
                except (ConnectionRefusedError, socket.timeout):
                    time.sleep(0.1)

            # A. Read the mandatory initial greeting capabilities negotiation banner from QEMU
            _ = self.qmp_sock.recv(4096)

            # B. Execute the mandatory QMP capabilities handshake command
            negotiate_cmd = json.dumps({"execute": "qmp_capabilities"}) + "\n"
            self.qmp_sock.sendall(negotiate_cmd.encode("utf-8"))

            # C. Read the execution acknowledgment response
            _ = self.qmp_sock.recv(4096)

            # Set to standard non-blocking/low-timeout mode for runtime status polling
            self.qmp_sock.settimeout(0.1)
        except Exception as e:
            logger.error(f"Failed to initialize raw QMP monitor connection: {e}")
            self.qmp_sock = None

    def stop(self) -> bool:
        """Safely shuts down the VM instance and releases process tree contexts."""
        if self.qmp_sock:
            try:
                # Send a clean system quit command down the monitor wire first
                quit_cmd = json.dumps({"execute": "quit"}) + "\n"
                self.qmp_sock.sendall(quit_cmd.encode("utf-8"))
            except Exception:
                pass
            self.qmp_sock.close()
            self.qmp_sock = None

        if self._process and self._process.poll() is None:
            try:
                import signal
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
            except Exception:
                self._process.kill()

        self._process = None
        self.console = None
        self.profile = None
        return True

    def status(self) -> Dict[str, Any]:
        """Queries the real hardware status straight via our explicit local QMP socket stream."""
        if not self._process or self._process.poll() is not None or not self.qmp_sock:
            return {"status": "STOPPED", "arch": None}
        try:
            status_cmd = json.dumps({"execute": "query-status"}) + "\n"
            self.qmp_sock.sendall(status_cmd.encode("utf-8"))

            response_bytes = self.qmp_sock.recv(4096)
            res = json.loads(response_bytes.decode("utf-8"))

            qmp_status = res.get("return", {}).get("status", "unknown")
            return {
                "status": qmp_status.upper(),
                "arch": self.profile.arch if self.profile else None
            }
        except Exception as e:
            return {"status": "RUNNING_QMP_ERROR", "arch": self.profile.arch if self.profile else None, "error": str(e)}

