import os
from typing import Optional
from fastmcp import FastMCP

from .qemu.vm import QEMUVirtualMachine
from .runtimes.base import TargetRuntime
from .runtimes.loader import detect_runtime

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
    
    :param kernel_path: Path to the target execution system image.
    :param profile: Configuration profile selection. Defaults to 'vxworks_x86_64_default'.
    :param extra_args: Additional space-separated hardware arguments to append to the command.
    """
    global active_runtime
    
    # 1. Forward both path and custom/default profile identifiers down to the hypervisor driver
    vm.start(kernel_path, profile_name=profile, extra_args=extra_args)
    active_runtime = None

    # 2. Structural Runtime Auto-Detection phase
    runtime_cls = detect_runtime(kernel_path)
    if runtime_cls:
        active_runtime = runtime_cls()
        return f"QEMU initialized with profile [{profile}]. Active Driver: {runtime_cls.__name__}"
    
    return f"QEMU initialized with profile [{profile}]. Warning: Target OS runtime driver missing."

@mcp.tool()
def stop_qemu() -> str:
    """Terminates the QEMU instance and releases runtime resources."""
    global active_runtime
    vm.stop()
    active_runtime = None
    return "Target environment completely stopped."


# =====================================================================
# UNIFIED RUNTIME APPLICATION TOOLS (Polymorphic 1:1 Layer)
# =====================================================================

@mcp.tool()
def app_upload(host_path: str, remote_path: str) -> str:
    """Uploads binaries or execution assets directly into the target environment."""
    if not active_runtime:
        return "Error: No target runtime environment is currently active."
    
    success = active_runtime.upload(host_path, remote_path)
    return "Upload successful." if success else "Failed to upload file to target."


@mcp.tool()
def app_exec(path: str, args: list[str] = None, options: dict = None) -> str:
    """Spawns an isolated execution unit (VxWorks RTP / Zephyr Thread) on the target."""
    if not active_runtime:
        return "Error: No target runtime environment is currently active."
    
    args = args or []
    options = options or {}
    
    # Explicitly returns the uniform string TargetID (e.g., RTP ID or TCB Ptr)
    target_id = active_runtime.exec(path, args, options)
    return f"Execution initiated successfully. Allocated Target ID: {target_id}"


@mcp.tool()
def app_kill(target_id: str) -> str:
    """Forces termination of an active application handle on the target OS."""
    if not active_runtime:
        return "Error: No target runtime environment is currently active."
    
    success = active_runtime.kill(target_id)
    return f"Termination signal sent to target [{target_id}]." if success else "Failed to kill target."


@mcp.tool()
def app_status(target_id: str) -> dict:
    """Queries the localized scheduling telemetry and execution states of an application."""
    if not active_runtime:
        return {"error": "No active target runtime."}
    
    # Returns the exact StatusJSON layout matching your schema specification
    return active_runtime.status(target_id)


@mcp.tool()
def target_inspect(mode: str) -> dict:
    """Performs a global system diagnostic snapshot (tasks, memory, fds)."""
    if not active_runtime:
        return {"error": "No active target runtime."}
    
    # Returns the exact StructuredJSON schema
    return active_runtime.inspect(mode)


@mcp.tool()
def app_fetch_logs(target_id: str, tail_lines: int = 100) -> str:
    """Retrieves context-isolated output buffers for an explicit application handle."""
    if not active_runtime:
        return "Error: No active target runtime."
    
    return active_runtime.fetch_logs(target_id, tail_lines)

