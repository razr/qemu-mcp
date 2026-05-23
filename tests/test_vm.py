# tests/test_vm.py
import os
import time
import pytest

from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.runtimes.detector import get_arch_info

def test_vm_backend_lifecycle_and_qmp(kernel_path):
    """
    Validates that QEMUVirtualMachine cleanly launches the underlying process,
    establishes a live QMP monitor handshake session alongside your custom 
    parameters, and tears down safely.
    """
    if not kernel_path:
        pytest.fail("Error: You must provide a path to a real kernel using: --kernel-path=<path>")

    if not os.path.exists(kernel_path):
        raise FileNotFoundError(f"Provided kernel file not found at: '{kernel_path}'")

    # 1. Resolve architecture from your real image to pick the matching profile configuration
    arch_info = get_arch_info(kernel_path)
    detected_arch = arch_info["arch"]  # 'x86_64'
    profile_name = f"vxworks_{detected_arch}_default"

    # 2. Instantiate your un-mocked QEMU hypervisor wrapper object
    vm = QEMUVirtualMachine()

    try:
        print("\n[STAGE 1] Booting hypervisor engine with combined base/custom parameters...")
        boot_success = vm.start(kernel_path=kernel_path, profile_name=profile_name)
        assert boot_success is True, "The VM backend start transaction returned False."

        # 3. Print out the absolute complete combined layout string to verify parity
        print("\n=================== RECONSTRUCTED RUNNING CMD ===================")
        if vm.machine and hasattr(vm.machine, 'args'):
            # Combine the internal base arguments and user added arguments to replicate the true execution string
            base_args = getattr(vm.machine, '_base_args', [])
            full_compiled_list = base_args + vm.machine.args
            print(f"{vm.machine.binary} " + " ".join(full_compiled_list))
        print("=================================================================\n")

        # Give QEMU a brief moment to stabilize the internal socket loops
        time.sleep(0.5)

        print("[STAGE 2] Querying hardware telemetry status over QMP...")
        vm_status = vm.status()
        print(f" -> Live Status Response Matrix: {vm_status}")
        
        # Enforce that the active QMP listener responds with a healthy state machine token
        assert vm_status["status"] == "RUNNING"
        assert vm_status["arch"] == "x86_64"

    finally:
        print("[STAGE 3] Invoking clean hardware shutdown sequence...")
        shutdown_success = vm.stop()
        assert shutdown_success is True, "VM stop sequence failed to return True context handle."
        
        # Verify tracking structures cleared accurately
        assert vm.machine is None
        assert vm.console is None
        print("[SUCCESS] VM implementation verified successfully from boot to tear down.")

