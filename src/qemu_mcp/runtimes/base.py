# src/qemu_mcp/runtimes/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class TargetRuntime(ABC):
    """
    Strict 1:1 Abstract Base Interface for QEMU-MCP Software Runtimes.
    All OS-specific concrete subclasses (VxWorks, Zephyr) must implement
    every method declared here with matching signatures.
    """

    # Each subclass must define its unique string token matching the profile 'os' field
    os_name: str = ""

    def __init__(self, vm_backend):
        """
        Initializes the runtime with a generic reference handle to the
        underlying hypervisor wrapper (QEMUVirtualMachine).
        """
        self.vm = vm_backend

    @abstractmethod
    def run_shell_command(self, command: str, timeout: float = 1.0) -> str:
        """
        Abstract transport contract interface.
        Sends an explicit string command down the target interactive text shell
        and returns the compiled terminal log outputs.
        """
        pass

    @abstractmethod
    def upload(self, host_path: str, remote_path: str) -> bool:
        """
        Transfers an asset (e.g. .vxe binary or .py script) into the target OS environment.
        """
        pass

    @abstractmethod
    def exec(self, path: str, args: List[str], options: Dict[str, Any]) -> str:
        """
        Spawns an isolated application execution unit on the target OS.
        Returns a unique, standardized string identifier (TargetID).
        """
        pass

    @abstractmethod
    def kill(self, target_id: str) -> bool:
        """
        Forces immediate termination of an active application handle on the target OS.
        """
        pass

    @abstractmethod
    def status(self, target_id: str) -> Dict[str, Any]:
        """
        Queries the execution state, health, and metadata of a specific application handle.
        Returns a structured dictionary matching StatusJSON.
        """
        pass

    @abstractmethod
    def fetch_logs(self, target_id: str, tail_lines: int = 100) -> str:
        """
        Retrieves context-isolated stdout/stderr output buffers for a specific application handle.
        """
        pass

    @abstractmethod
    def inspect(self, mode: str) -> Dict[str, Any]:
        """
        Performs a global system-wide diagnostic snapshot of an OS subsystem.
        Modes: 'tasks', 'memory', 'fds'. Returns a structured dictionary matching StructuredJSON.
        """
        pass

