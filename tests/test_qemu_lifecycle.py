# tests/test_qemu_lifecycle.py
import os
import time
import pytest
from qemu.machine.machine import QEMUMachineError

from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.runtimes.detector import get_arch_info

def test_qemu_vxworks_lifecycle(kernel_path):
    """
    Validates the QEMU launch sequence and dumps the background console
    on crash to expose missing hypervisor parameters.
    """
    if not kernel_path:
        pytest.fail("Error: You must provide a path to a real kernel using: --kernel-path=<path>")

    if not os.path.exists(kernel_path):
        raise FileNotFoundError(f"Provided kernel file not found at: '{kernel_path}'")

    arch_info = get_arch_info(kernel_path)
    detected_arch = arch_info["arch"]
    profile_name = f"vxworks_{detected_arch}_default"

    print(f"\n[INFO] Auto-selected configuration profile: {profile_name}")

    vm = QEMUVirtualMachine()

    try:
        print("[STAGE 1] Launching QEMU subprocess pipeline...")
        vm.start(kernel_path=kernel_path, profile_name=profile_name)

        time.sleep(0.5)
        print("[STAGE 2] Querying live machine status via QMP socket...")
        vm_status = vm.status()
        print(f" -> Retrieved Hypervisor Status Matrix: {vm_status}")
        assert vm_status["status"] == "RUNNING"

    except (QEMUMachineError, Exception) as e:
        print(f"\n[CRITICAL ERROR] QEMU failed to establish a handshake: {e}")
        print("=================== QEMU CONSOLE DUMP ===================")

        # Read the exact background console output log to capture why the kernel faulted
        log_path = getattr(vm, 'log_path', '/app/qemu_vms.log')
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                print(f.read())
        else:
            print(f"Log file not found at {log_path}. checking QEMU process stderr instead...")
            if vm.machine and hasattr(vm.machine, 'get_log'):
                print(vm.machine.get_log())

        print("=========================================================")
        pytest.fail("QEMU subprocess crashed immediately upon execution.")

    finally:
        print("[STAGE 3] Triggering hypervisor shutdown sequence...")
        vm.stop()

