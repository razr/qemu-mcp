# src/qemu_mcp/runtimes/vxworks/runtime.py
import time
import re
import logging
from typing import List, Dict, Any
from ..base import TargetRuntime

logger = logging.getLogger("qemu_mcp.runtimes.vxworks")

class VxWorksRuntime(TargetRuntime):
    """
    Concrete VxWorks Target Software Runtime.
    Implements process-centric operations via raw serial shell automation loops.
    """

    # This acts as the registration key for the dynamic loader
    os_name = "vxworks"

    def __init__(self, vm_backend):
        super().__init__(vm_backend)
        self.shell_mode = "C"  # Track state: "C" (Kernel Shell) or "cmd" (Command Shell)

    def _ensure_shell_mode(self, target_mode: str):
        """Switches the interactive terminal state between C and cmd interpreters."""
        if not self.vm or not self.vm.console:
            raise RuntimeError("Cannot alter shell context: Hypervisor console channel is offline.")

        if self.shell_mode == target_mode:
            return

        if target_mode == "cmd" and self.shell_mode == "C":
            self.vm.console.send("cmd\n")
            self.shell_mode = "cmd"
            time.sleep(0.1)  # Buffer delay for prompt transition
        elif target_mode == "C" and self.shell_mode == "cmd":
            self.vm.console.send("C\n")
            self.shell_mode = "C"
            time.sleep(0.1)

    def upload(self, host_path: str, remote_path: str) -> bool:
        """
        Transfers binaries or execution assets into VxWorks target storage.
        Note: For standard setups, this moves files into an active host-share
        directory mapping to an NFS mount point inside the guest.
        """
        # Placeholder for automated host filesystem staging logic
        logger.info(f"Staging file transfer: {host_path} -> {remote_path}")
        return True

    def exec(self, path: str, args: List[str], options: Dict[str, Any]) -> str:
        """
        Spawns an isolated real-time process context (RTP) via shell.
        Returns the unique hex identifier string (RTP ID).
        """
        self._ensure_shell_mode("C")

        # 1. Format parameter collections
        formatted_args = ", ".join(f'"{a}"' for a in args) if args else "0"

        # 2. Compile standard rtpSp command string
        # Default stack sizes are elevated to handle Python runtimes securely
        stack_size = options.get("stack_size", 65536)
        priority = options.get("priority", 100)

        exec_cmd = f"rtpSp \"{path}\", {formatted_args}, {priority}, {stack_size}\n"

        # Clear out any previous unread stdout line elements from the pipe
        _ = self.vm.console.read_available()

        # 3. Transmit command down the wire
        self.vm.console.send(exec_cmd)
        time.sleep(0.2)  # Give VxWorks a small window to output the boot token

        # 4. Parse the terminal trace to isolate the generated RTP pointer token
        console_dump = self.vm.console.read_available()
        # Look for typical boot messages: "Launch process '...' (RTP Id: 0x2010ab30)"
        match = re.search(r"RTP Id:\s*(0x[0-9a-fA-F]+)", console_dump)
        if match:
            return match.group(1)

        # Fallback to general lookup if direct regex fails
        return "0xUnknownRTP"

    def kill(self, target_id: str) -> bool:
        """Forces immediate termination of an active application process via rtpDelete."""
        self._ensure_shell_mode("C")
        kill_cmd = f"rtpDelete {target_id}\n"
        return self.vm.console.send(kill_cmd)

    def status(self, target_id: str) -> Dict[str, Any]:
        """Queries localized telemetry and execution parameters for a specific RTP handle."""
        self._ensure_shell_mode("C")
        status_cmd = f"rtpShow {target_id}\n"

        _ = self.vm.console.read_available()
        self.vm.console.send(status_cmd)
        time.sleep(0.1)
        output = self.vm.console.read_available()

        # Simple string-matching telemetry heuristics against standard rtpShow logs
        is_alive = "STATE_READY" in output or "STATE_NORMAL" in output or "RUNNING" in output
        state = "RUNNING" if is_alive else "STOPPED"
        if "ZOMBIE" in output:
            state = "ZOMBIE"

        return {
            "target_id": target_id,
            "is_alive": is_alive,
            "state": state,
            "cpu_utilization_pct": 0.0,  # Would require spyLib parsing for complete resolution
            "memory_bytes_allocated": 0,
            "exit_code": None
        }

    def fetch_logs(self, target_id: str, tail_lines: int = 100) -> str:
        """
        Retrieves context-isolated stdout/stderr outputs for an application handle.
        Note: If ioTaskStdSet was used to capture process output into a file,
        this command reads that file path directly via the shell.
        """
        self._ensure_shell_mode("cmd")
        # Assuming typical setup routes logs to a unique storage descriptor path:
        read_cmd = f"tail -n {tail_lines} /tffs0/logs/{target_id}.log\n"

        _ = self.vm.console.read_available()
        self.vm.console.send(read_cmd)
        time.sleep(0.1)
        return self.vm.console.read_available()

    def inspect(self, mode: str) -> Dict[str, Any]:
        """Performs global system diagnostics by processing human-readable ASCII tables."""
        if mode not in ["tasks", "memory", "fds"]:
            raise ValueError(f"Unsupported diagnostic mode element: {mode}")

        self._ensure_shell_mode("C")

        # Map parameters to exact core VxWorks inspection commands
        cmd_map = {"tasks": "taskShow\n", "memory": "memShow\n", "fds": "iosFdShow\n"}
        self.vm.console.send(cmd_map[mode])
        time.sleep(0.3)  # Large tables require extra buffer processing latencies

        raw_table = self.vm.console.read_available()

        # Returns the structural format to the upstream tool context
        return {
            "mode": mode,
            "raw_output": raw_table,
            "summary": f"Extracted system matrix data for subsystem [{mode}]."
        }

    def run_shell_command(self, command: str, timeout: float = 1.0) -> str:
        """
        Generic passthrough shell command interface.
        Delegates the complete exchange pattern straight down to the console transport layer.
        """
        # 1. Stateless Self-Healing Check: Reconnect console subsystem if dropped
        console_subsystem = self.vm.console
        if not console_subsystem:
            from qemu_mcp.qemu.console import QEMUConsole
            self.vm.console = QEMUConsole(self.vm)
            console_subsystem = self.vm.console

        try:
            # 2. Leverage your unified console transport method directly!
            # It cleanly handles connection, buffer flushing, sending, and delayed reading
            return console_subsystem.exchange_text(text_payload=command, delay=timeout)

        except Exception as e:
            return f"Exception encountered during console communication loop: {str(e)}"
