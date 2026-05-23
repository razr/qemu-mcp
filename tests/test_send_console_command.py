# tests/test_send_console_command.py
import os
import time
import pytest

from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.runtimes.detector import get_arch_info
from qemu_mcp.qemu.profile import QEMUProfile
from qemu_mcp.runtimes.loader import get_runtime_class

def test_runtime_generic_send_console_command_integration(kernel_path):
    """
    Real hardware integration test for the polymorphic send_console_command workflow.
    Validates that a fresh runtime class can attach to a running QEMU daemon,
    transmit text down the serial socket, and read back the raw execution results.
    """
    if not kernel_path:
        pytest.fail("Error: You must provide a path to a real kernel using: --kernel-path=<path>")

    if not os.path.exists(kernel_path):
        raise FileNotFoundError(f"Provided kernel file not found at: '{kernel_path}'")

    # 1. Resolve architectural settings dynamically
    arch_info = get_arch_info(kernel_path)
    profile_name = f"vxworks_{arch_info['arch']}_default"

    profile = QEMUProfile(log_path="qemu_vms.log", profile_name=profile_name)
    qemu_bin = os.path.basename(profile.qemu_bin)

    # 2. Hard clean previous lingering processes
    os.system(f"pkill -9 -x {qemu_bin} 2>/dev/null")

    # Force the local host target loop back to test natively
    os.environ["MCP_QEMU_HOST"] = "127.0.0.1"

    vm_starter = QEMUVirtualMachine()

    try:
        print("\n[CONSOLE TEST STAGE 1] Launching persistent QEMU hypervisor loop...")
        boot_success = vm_starter.start(kernel_path=kernel_path, profile_name=profile_name)
        assert boot_success is True

        # Give the guest OS kernel enough time to finish boot sequence initialization
        print("Waiting for VxWorks kernel to complete boot banner cycles...")
        time.sleep(5.0)

        # Simulate FastMCP Tool boundary end: Destroy the starting object completely
        del vm_starter
        print("[CONSOLE TEST STAGE 1.5] Memory wiped out to simulate stateless FastMCP lifecycles.")

        # -------------------------------------------------------------------
        # SIMULATE STATELESS INTERACTIVE KEYSTROKE INJECT
        # -------------------------------------------------------------------
        print("[CONSOLE TEST STAGE 2] Initializing fresh stateless context structures...")
        vm_operator = QEMUVirtualMachine()

        # Verify the self-healing monitor confirms QEMU is running independently
        status_matrix = vm_operator.status()
        assert status_matrix.get("status") == "RUNNING"

        # Instantiate a brand new runtime class driver using your loader hooks
        runtime_cls = get_runtime_class("vxworks")
        assert runtime_cls is not None

        active_runtime = runtime_cls(vm_operator)

        print(" -> Transmitting command 'version' down the raw serial socket channel...")
        # Execute your generic pass-through console execution string tool block
        console_output = active_runtime.run_shell_command(command="version", timeout=1.5)
        print("\n------------------ CAPTURED CONSOLE OUTPUT ------------------")
        print(console_output)
        print("--------------------------------------------------------------\n")

        # Assertions to prove data returned from the real VxWorks kernel wire shell
        assert "Error" not in console_output
        assert "unreachable" not in console_output
        assert "VxWorks" in console_output or "-> " in console_output

    finally:
        print("[CONSOLE TEST STAGE 3] Sending native clean QMP quit sequence down the wire...")
        vm_cleanup = QEMUVirtualMachine()
        vm_cleanup.stop(binary_name=qemu_bin)
        del vm_cleanup

        time.sleep(0.5)
        os.system(f"pkill -9 -x {qemu_bin} 2>/dev/null")
