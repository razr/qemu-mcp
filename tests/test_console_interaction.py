# tests/test_console_interaction.py
import os
import time
import pytest

from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.runtimes.detector import get_arch_info

def test_vxworks_console_interaction(kernel_path):
    """
    Validates that QEMUConsole can interactively drain the boot stream
    and send shell expressions down the serial wire dynamically.
    """
    if not kernel_path:
        pytest.fail("Error: You must provide a path to a real kernel using: --kernel-path=<path>")

    arch_info = get_arch_info(kernel_path)
    profile_name = f"vxworks_{arch_info['arch']}_default"

    vm = QEMUVirtualMachine()

    try:
        print("\n[STAGE 1] Booting VxWorks kernel...")
        vm.start(kernel_path=kernel_path, profile_name=profile_name)

        print("\n=================== ACTUAL QEMU COMMAND LINE ===================")
        if hasattr(vm, 'args') and vm.args:
            full_command = f"{vm.binary} " + " ".join(vm.args)
            print(full_command)
        print("================================================================\n")

        # --- FIX: RE-CONNECT SOCKET FRESHLY TO SWALLOW THE ACCUMULATED BACKLOG ---
        # This acts exactly like running 'nc 127.0.0.1 15555' right as the VM finishes spawning!
        if vm.console.sock:
            vm.console.sock.close()
            vm.console.sock = None
        vm.console._connect_socket()
        # -------------------------------------------------------------------------

        # --- DYNAMIC POLLING LOOP WITH TIMEOUT ---
        print("[STAGE 2] Waiting dynamically for VxWorks boot banner...")
        boot_logs = ""
        timeout = 10.0
        start_time = time.time()
        banner_found = False

        while time.time() - start_time < timeout:
            chunk = vm.console.read_available()
            if chunk:
                boot_logs += chunk
                if "VxWorks" in boot_logs:
                    banner_found = True
                    print(f" -> Success: Captured boot banner in {time.time() - start_time:.2f} seconds.")
                    break
            time.sleep(0.1)

        print("------------------ CAPTURED BOOT LOGS ------------------")
        print(boot_logs or "(Buffer empty)")
        print("--------------------------------------------------------")

        if not banner_found:
            pytest.fail("Execution Timeout Error: VxWorks boot banner was not detected within 10 seconds.")

        print("[STAGE 3] Injecting newline to awake the target shell prompt...")
        vm.console.send("\n")
        time.sleep(0.5)

        prompt_check = vm.console.read_available()
        print(f" -> Shell Response Fragment: {repr(prompt_check)}")
        assert "->" in prompt_check, f"Expected VxWorks prompt token '->', got: {repr(prompt_check)}"

    finally:
        print("[STAGE 4] Shutting down target engine...")
        vm.stop()

