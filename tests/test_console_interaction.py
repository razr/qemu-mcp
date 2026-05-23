# tests/test_console_interaction.py
import os
import time
import pytest

from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.runtimes.detector import get_arch_info

def test_vxworks_console_interaction(kernel_path):
    """
    Validates that QEMUConsole can interactively drain the boot stream
    and send shell expressions down the serial wire.
    """
    if not kernel_path:
        pytest.fail("Error: You must provide a path to a real kernel using: --kernel-path=<path>")

    arch_info = get_arch_info(kernel_path)
    profile_name = f"vxworks_{arch_info['arch']}_default"

    vm = QEMUVirtualMachine()

    try:
        print("\n[STAGE 1] Booting VxWorks kernel...")
        vm.start(kernel_path=kernel_path, profile_name=profile_name)

        # ----------------------------------------------------------------------
        # PRINT COMPRESSED / ACTUAL COMMAND LINE PASSED TO GENERATED SUBPROCESS
        # ----------------------------------------------------------------------
        print("\n=================== ACTUAL QEMU COMMAND LINE ===================")
        if vm.machine and hasattr(vm.machine, 'args'):
            # Join the generated property list tokens cleanly into a copy-pasteable string block
            full_command = f"{vm.machine.binary} " + " ".join(vm.machine.args)
            print(full_command)
        else:
            print("(Unable to extract args from the running hypervisor instance layout)")
        print("================================================================\n")

        # Give the real-time kernel 3 seconds to complete initial device initialization
        time.sleep(10.0)

        print("[STAGE 2] Draining non-blocking boot log buffer...")
        boot_logs = vm.console.read_available()

        print("------------------ CAPTURED BOOT LOGS ------------------")
        print(boot_logs or "(Buffer empty)")
        print("--------------------------------------------------------")

        # Verify that the core kernel banner elements exist inside the read text chunk
        assert "VxWorks" in boot_logs, "Failed to capture the Wind River kernel boot signature"

        print("[STAGE 3] Injecting newline to awake the target shell prompt...")
        vm.console.send("\n")
        time.sleep(0.5)

        prompt_check = vm.console.read_available()
        print(f" -> Shell Response Fragment: {repr(prompt_check)}")
        assert "->" in prompt_check, f"Expected VxWorks prompt token '->', got: {repr(prompt_check)}"

    finally:
        print("[STAGE 4] Shutting down target engine...")
        vm.stop()

