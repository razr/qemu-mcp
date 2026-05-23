# tests/test_server.py
import os
import time
import pytest

from qemu_mcp.server import start_qemu, get_qemu_status, stop_qemu
from qemu_mcp.runtimes.detector import get_arch_info

def test_server_tools_lifecycle_integration(kernel_path):
    """
    Validates the end-to-end orchestration flow via the exposed FastMCP tool layer.
    Verifies initialization, status queries via QMP, and clean shutdown.
    """
    if not kernel_path:
        pytest.fail("Error: You must provide a path to a real kernel using: --kernel-path=<path>")

    if not os.path.exists(kernel_path):
        raise FileNotFoundError(f"Provided kernel file not found at: '{kernel_path}'")

    # 1. Resolve architectural signature to pick the default profile
    arch_info = get_arch_info(kernel_path)
    profile_name = f"vxworks_{arch_info['arch']}_default"

    try:
        print(f"\n[STAGE 1] Triggering 'start_qemu' tool function via profile [{profile_name}]...")
        # Invoke the actual FastMCP tool function directly
        boot_msg = start_qemu(kernel_path=kernel_path, profile=profile_name)
        print(f" -> Server Response Message: {repr(boot_msg)}")

        assert "QEMU initialized" in boot_msg or "Connected runtime" in boot_msg
        assert "Error" not in boot_msg

        # Give the hardware hypervisor a brief moment to stabilize socket threads
        time.sleep(0.5)

        print("[STAGE 2] Triggering 'get_qemu_status' tool function over active QMP socket...")
        # Verify that the server's telemetry tool queries the JSON-RPC interface successfully
        status_matrix = get_qemu_status()
        print(f" -> Server Telemetry Matrix: {status_matrix}")

        assert status_matrix["status"] == "RUNNING"
        assert status_matrix["arch"] == "x86_64"

    finally:
        print("[STAGE 3] Triggering 'stop_qemu' tool function to tear down hypervisor...")
        # Verify resources clean up completely
        stop_msg = stop_qemu()
        print(f" -> Teardown Response Message: {repr(stop_msg)}")
        assert "completely stopped" in stop_msg or "already stopped" in stop_msg

