# tests/test_vm.py
import os
import time
import pytest
from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.runtimes.detector import get_arch_info

def test_vm_backend_lifecycle_and_qmp(kernel_path):
    if not kernel_path:
        pytest.fail("Error: Provide a kernel path using: --kernel-path=<path>")

    arch_info = get_arch_info(kernel_path)
    profile_name = f"vxworks_{arch_info['arch']}_default"
    vm = QEMUVirtualMachine()

    try:
        print("\n[STAGE 1] Booting hypervisor engine with pure subprocess wrapper...")
        boot_success = vm.start(kernel_path=kernel_path, profile_name=profile_name)
        assert boot_success is True

        print("\n=================== RECONSTRUCTED RUNNING CMD ===================")
        print(f"{vm.binary} " + " ".join(vm.args))
        print("=================================================================\n")

        time.sleep(0.5)

        print("[STAGE 2] Querying hardware telemetry status over raw QMP socket...")
        vm_status = vm.status()
        print(f" -> Live Status Response Matrix: {vm_status}")

        assert vm_status["status"] == "RUNNING"
        assert vm_status["arch"] == "x86_64"

    finally:
        print("[STAGE 3] Invoking clean hardware shutdown sequence...")
        assert vm.stop() is True

