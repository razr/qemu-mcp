import os
from fastmcp import FastMCP
from .manager import QEMUManager

# Initialize FastMCP and the Business Logic Manager
mcp = FastMCP("QEMU-Manager")
manager = QEMUManager()

@mcp.tool()
def start_qemu(kernel_path: str, extra_args: str = None) -> str:
    """
    Starts a QEMU instance. Automatically detects architecture from the kernel file.
    :param kernel_path: Absolute path to the vxWorks or RTOS kernel binary.
    :param extra_args: Optional additional QEMU command line arguments.
    """
    return manager.start(kernel_path, extra_args)

@mcp.tool()
def stop_qemu() -> str:
    """Safely shuts down the running QEMU instance and cleans up sockets."""
    return manager.stop()

@mcp.tool()
def get_status() -> str:
    """Returns the current execution status of the VM via QMP."""
    return manager.status()

@mcp.tool()
def get_console_output(lines: int = 50):
    """
    Reads the last N lines of the QEMU serial console log.
    Use this to check the vxWorks boot sequence or debug crashes.
    """
    log_path = "/app/qemu_vms.log"
    if not os.path.exists(log_path):
        return "No log file found. VM might not be running or log is empty."

    with open(log_path, "r") as f:
        content = f.readlines()
        return "".join(content[-lines:])

@mcp.tool()
def rtp_exec(rtp_name: str) -> str:
    """
    Executes an RTP. Automatically switches to cmd mode if needed.
    """
    # 1. Ensure we are in the correct shell for 'rtp exec'
    manager.ensure_cmd_mode()

    # 2. Execute the command
    command = f"rtp exec {rtp_name}\n"
    if manager.send_input(command):
        return f"Ensured cmd mode and executed: {command.strip()}"
    return "Error: Could not send command to QEMU"

@mcp.tool()
def toggle_shell() -> str:
    """Toggles between C and cmd shell."""
    if manager.shell_mode == "C":
        manager.send_input("cmd\n")
        manager.shell_mode = "cmd"
    else:
        manager.send_input("C")
        manager.shell_mode = "C"
    return f"Shell toggled to: {manager.shell_mode}"

