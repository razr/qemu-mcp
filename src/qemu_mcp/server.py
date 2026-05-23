# src/qemu_mcp/server.py
import os
import logging
from typing import Optional, List, Dict, Any
from fastmcp import FastMCP

from .qemu.vm import QEMUVirtualMachine
from .runtimes.base import TargetRuntime
from .runtimes.loader import get_runtime_class
from .qemu.profile import PROFILES

logger = logging.getLogger("qemu_mcp.server")

# 1. Initialize FastMCP with a fixed, predictable capability matrix
mcp = FastMCP("QEMU-MCP-Manager")

# Global hypervisor and active runtime infrastructure references
vm = QEMUVirtualMachine()
active_runtime: Optional[TargetRuntime] = None


# =====================================================================
# HYPERVISOR MANAGEMENT TOOLS (QEMU Backend Layer)
# =====================================================================

@mcp.tool()
def start_qemu(kernel_path: str, profile: str = "vxworks_x86_64_default", extra_args: str = None) -> str:
    """
    Boots the QEMU engine utilizing an explicit or default parameter configuration profile.
    """
    global active_runtime

    if profile not in PROFILES:
        return f"Error: Configuration profile '{profile}' is unrecognized."

    boot_success = vm.start(kernel_path, profile_name=profile, extra_args=extra_args)
    if not boot_success:
        return "Error: Hypervisor failed to boot or a target engine instance is already active."

    active_runtime = None

    # FIXED: Check the profile dictionary configuration metadata to find the matching 'os' token
    os_name = PROFILES[profile]["os"]  # 'vxworks'

    # 2. Structural Runtime Auto-Detection phase
    runtime_cls = get_runtime_class(os_name)  # FIXED: Use your verified loader API method
    if runtime_cls:
        active_runtime = runtime_cls(vm)
        return f"QEMU initialized with profile [{profile}]. Active Driver: {runtime_cls.__name__}"

    return f"QEMU initialized with profile [{profile}]. Warning: Target OS runtime driver missing."

@mcp.tool()
def stop_qemu() -> str:
    """Terminates the active QEMU instance and releases runtime resources."""
    global active_runtime
    if vm.stop():
        active_runtime = None
        return "Target environment completely stopped."
    return "Hypervisor is already stopped."


@mcp.tool()
def get_qemu_status() -> dict:
    """Queries the low-level hardware virtualization status over the raw QMP socket loop."""
    # Instantly hits loopback port 15556 via json-rpc execution packets
    return vm.status()

@mcp.tool()
def send_console_command(command: str, timeout: float = 1.0) -> str:
    """
    Sends an explicit text command down the runtime's interactive target shell interface
    and harvests the returned string logs.
    """
    global active_runtime

    # Stateless Self-Healing: Reconstruct the runtime driver context if FastMCP wiped it out
    if not active_runtime:
        status_info = vm.status()
        if status_info.get("status") == "RUNNING":
            from .runtimes.loader import get_runtime_class
            runtime_cls = get_runtime_class("vxworks")
            if runtime_cls:
                active_runtime = runtime_cls(vm)

    # If it's still missing, it means the hypervisor process is completely stopped
    if not active_runtime:
        return "Error: No target runtime environment is currently active. Call start_qemu first."

    # Execute your generic passthrough method through your polymorphic driver layer
    return active_runtime.run_shell_command(command=command, timeout=timeout)

# =====================================================================
# UNIFIED RUNTIME APPLICATION TOOLS (Polymorphic 1:1 Layer)
# =====================================================================

@mcp.tool()
def app_upload(host_path: str, remote_path: str) -> str:
    """Uploads binaries or execution assets directly into the target environment."""
    if not active_runtime:
        return "Error: No target runtime environment is currently active. Call start_qemu first."

    success = active_runtime.upload(host_path, remote_path)
    return "Upload successful." if success else "Failed to upload file to target."


@mcp.tool()
def app_exec(path: str, args: List[str] = None, options: dict = None) -> str:
    """Spawns an isolated execution unit (VxWorks RTP / Zephyr Thread) on the target."""
    if not active_runtime:
        return "Error: No target runtime environment is currently active. Call start_qemu first."

    args = args or []
    options = options or {}

    # Explicitly returns the uniform string TargetID (e.g., RTP ID or TCB Ptr)
    target_id = active_runtime.exec(path, args, options)
    return f"Execution initiated successfully. Allocated Target ID: {target_id}"


@mcp.tool()
def app_kill(target_id: str) -> str:
    """Forces termination of an active application handle on the target OS."""
    if not active_runtime:
        return "Error: No target runtime environment is currently active. Call start_qemu first."

    success = active_runtime.kill(target_id)
    return f"Termination signal sent to target [{target_id}]." if success else "Failed to kill target."


@mcp.tool()
def app_status(target_id: str) -> dict:
    """Queries the localized scheduling telemetry and execution states of an application."""
    if not active_runtime:
        return {"error": "No active target runtime. Call start_qemu first."}

    # Returns the exact StatusJSON layout matching your schema specification
    return active_runtime.status(target_id)


@mcp.tool()
def target_inspect(mode: str) -> dict:
    """Performs a global system diagnostic snapshot (tasks, memory, fds)."""
    if not active_runtime:
        return {"error": "No active target runtime. Call start_qemu first."}

    # Returns the exact StructuredJSON schema by sending commands down loopback port 15555
    return active_runtime.inspect(mode)


@mcp.tool()
def app_fetch_logs(target_id: str, tail_lines: int = 100) -> str:
    """Retrieves context-isolated output buffers for an explicit application handle."""
    if not active_runtime:
        return "Error: No active target runtime. Call start_qemu first."

    return active_runtime.fetch_logs(target_id, tail_lines)

