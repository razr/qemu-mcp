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
def list_profiles() -> str:
    """
    List the QEMU configuration profiles supported out of the box.

    Use this to discover which `profile` values `start_qemu` accepts, and what each
    one targets (OS/arch, networking, whether it needs a `drive_image`, and whether a
    telnet second console is reachable). Returns one line per profile.

    Second console: the serial console is always the primary (boot/EDR/crash) channel.
    Profiles on a `tap` backend also expose the target over telnet at its static IP
    (telnetd runs by default) — use the `connect_telnet` tool for a clean interactive
    channel (e.g. a subscriber on telnet while a publisher runs on serial). user-net
    (slirp) profiles are NAT'd, so telnet is not directly reachable at that IP.
    """
    import re
    lines = []
    for name, p in PROFILES.items():
        needs_disk = any("{drive_image}" in a for a in p.get("drive_args", []))
        net_list = p.get("network_args", [])
        net = " ".join(net_list) or "none"
        accel = "kvm" if any("-enable-kvm" in a for a in p.get("platform_args", [])) else "tcg"
        # Telnet second path: reachable on a tap backend at the target IP from the
        # boot line's e= field; NAT'd (not directly reachable) on user-net.
        is_tap = any("tap" in a for a in net_list)
        telnet = "no (user-net/NAT)"
        if is_tap:
            m = re.search(r"\be=([0-9.]+)", p.get("append_args", "") or "")
            ip = m.group(1) if m else "192.168.200.1"
            telnet = f"{ip}:23 (connect_telnet)"
        lines.append(
            f"{name}: os={p['os']} arch={p['arch']} accel={accel} "
            f"mem={p.get('memory','?')} net=[{net}] "
            f"drive_image={'required' if needs_disk else 'no'} "
            f"telnet={telnet}"
        )
    return "Available QEMU profiles:\n" + "\n".join(lines)


@mcp.tool()
def start_qemu(kernel_path: str, profile: str = "vxworks_x86_64_default",
               extra_args: str = None, drive_image: str = None,
               wait_boot: bool = True, boot_timeout: float = 120.0) -> str:
    """
    Boots the QEMU engine utilizing an explicit or default parameter configuration profile.

    drive_image (disk-image profiles only): absolute path to the RAW FAT disk image
    to attach. The server does NOT hardcode or locate it — pass the image your board
    build system produces (its 'make image'/deploy output), or one generated per the
    README (dd + mkfs.vfat + mcopy). drive_args() raises if a disk profile is used
    without a drive_image. When wait_boot is True, blocks until the target prints a
    boot-ready marker and the command shell is entered.
    """
    global active_runtime

    if profile not in PROFILES:
        return f"Error: Configuration profile '{profile}' is unrecognized."

    # Arch compatibility: the kernel ELF's machine must match the profile's QEMU arch,
    # otherwise QEMU boots the wrong qemu-system-* and the target silently hangs. A
    # definite mismatch is refused; an unreadable/non-ELF kernel is a warning (don't
    # block exotic kernels). The disk image inherits the kernel's arch, so checking
    # the kernel is sufficient.
    try:
        from .runtimes.detector import get_arch_info
        info = get_arch_info(kernel_path)
        kernel_arch = info["arch"]
        profile_arch = PROFILES[profile]["arch"]
        if kernel_arch != profile_arch:
            return (
                f"Error: architecture mismatch — kernel '{kernel_path}' is "
                f"{kernel_arch} but profile '{profile}' targets {profile_arch}. "
                f"Pick a {kernel_arch} profile (e.g. qemu_bin "
                f"qemu-system-{kernel_arch})."
            )
    except FileNotFoundError:
        return f"Error: kernel image not found: {kernel_path}"
    except Exception as e:
        # Non-ELF or unsupported machine: warn via log, proceed (caller may know best).
        logger.warning("arch compat check skipped for %s: %s", kernel_path, e)

    boot_success = vm.start(kernel_path, profile_name=profile,
                            extra_args=extra_args, drive_image=drive_image)
    if not boot_success:
        return "Error: Hypervisor failed to boot or a target engine instance is already active."

    # Remember the image so the runtime's upload() can mcopy into it.
    vm.drive_image = drive_image

    active_runtime = None
    os_name = PROFILES[profile]["os"]
    runtime_cls = get_runtime_class(os_name)
    if runtime_cls:
        active_runtime = runtime_cls(vm)

    msg = f"QEMU initialized with profile [{profile}]."
    if runtime_cls:
        msg += f" Active Driver: {runtime_cls.__name__}."
    else:
        msg += " Warning: Target OS runtime driver missing."

    if wait_boot:
        booted = vm.wait_for_boot(timeout=boot_timeout)
        if not booted:
            return msg + f" WARNING: boot-ready marker not seen within {boot_timeout}s."
        msg += " Boot-ready marker detected."
        # Enter the command shell once so subsequent commands are reliable.
        if active_runtime and hasattr(active_runtime, "enter_command_shell"):
            if active_runtime.enter_command_shell():
                msg += " Command shell ready."
            else:
                msg += " WARNING: could not confirm command shell."
        # Try the dedicated telnet shell (telnetd runs by default on many VxWorks images).
        if active_runtime and hasattr(active_runtime, "connect_telnet"):
            if active_runtime.connect_telnet():
                active_runtime.enter_command_shell()
                msg += " Telnet shell connected (clean interactive channel)."
            else:
                msg += " (telnet not available; using serial console)."
    return msg

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


# =====================================================================
# VXWORKS DIAGNOSTIC TOOLS (fault capture + kernel routines)
# =====================================================================

@mcp.tool()
def app_exec_detailed(path: str, args: List[str] = None, stack_size: str = None,
                      timeout: float = 30.0) -> dict:
    """Launch an RTP by path and return a classified outcome with raw console text.

    outcome is one of: LAUNCHED (with rtp_id), INSTANTIATE_FAILED, SIGNAL_<n>, NO_LAUNCH.
    stack_size (e.g. '0x10000000') raises rtpSpStackSize before launch.
    """
    if not active_runtime:
        return {"error": "No active target runtime. Call start_qemu first."}
    if not hasattr(active_runtime, "exec_detailed"):
        return {"error": "Active runtime does not support exec_detailed."}
    opts = {"timeout": timeout}
    if stack_size:
        opts["stack_size"] = stack_size
    return active_runtime.exec_detailed(path, args or [], opts)


@mcp.tool()
def run_kernel_routine(routine: str, timeout: float = 15.0) -> str:
    """Run a VxWorks C/kernel-shell routine (e.g. 'taskShow', 'rtpShow 0x..') from the
    command shell via the 'C <routine>' prefix. No shell switching required."""
    if not active_runtime:
        return "Error: No active target runtime. Call start_qemu first."
    if not hasattr(active_runtime, "run_kernel_routine"):
        return "Error: Active runtime has no kernel-routine support."
    return active_runtime.run_kernel_routine(routine, timeout=timeout)


@mcp.tool()
def connect_telnet(host: str = "192.168.200.1", port: int = 23, retries: int = 20) -> str:
    """Open a dedicated telnet shell to the VxWorks target (telnetd runs by default).

    Telnet is a clean interactive channel; the serial console remains the boot/EDR/
    crash channel. After connecting, interactive commands route over telnet while
    crash/INSTANTIATE detection still watches serial."""
    if not active_runtime:
        return "Error: No active target runtime. Call start_qemu first."
    if not hasattr(active_runtime, "connect_telnet"):
        return "Error: Active runtime has no telnet support."
    if active_runtime.connect_telnet(host=host, port=port, retries=retries):
        active_runtime.enter_command_shell()
        return f"Telnet shell connected to {host}:{port}."
    return f"Failed to connect telnet to {host}:{port}."


@mcp.tool()
def edr_show(timeout: float = 20.0) -> dict:
    """Dump + parse the VxWorks EDR fatal record after a crash.

    Returns the Program Counter (pc), fault/access_address, exception, task, and the
    raw edrShow text. Use after an RTP dies with signal 11 to classify the fault:
      - pc == access_address  -> jumped to a bad/corrupt function pointer
      - access_address tiny    -> NULL / near-null deref
      - access_address huge    -> unmapped/protected memory access
    """
    if not active_runtime:
        return {"error": "No active target runtime. Call start_qemu first."}
    if not hasattr(active_runtime, "edr_show"):
        return {"error": "Active runtime does not support edr_show."}
    return active_runtime.edr_show(timeout=timeout)

