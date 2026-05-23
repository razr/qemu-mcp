# tests/test_vm.py
import os
import time
import pytest
from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.runtimes.detector import get_arch_info
from qemu_mcp.qemu.profile import QEMUProfile

def test_vm_backend_lifecycle_and_qmp(kernel_path):
    if not kernel_path:
        pytest.fail("Error: Provide a kernel path using: --kernel-path=<path>")

    if not os.path.exists(kernel_path):
        raise FileNotFoundError(f"Provided kernel file not found at: '{kernel_path}'")

    # 1. Dynamically get the architecture profile
    arch_info = get_arch_info(kernel_path)
    profile_name = f"vxworks_{arch_info['arch']}_default"

    # 2. Extract the exact binary target name generically
    profile = QEMUProfile(log_path="qemu_vms.log", profile_name=profile_name)
    qemu_bin = os.path.basename(profile.qemu_bin) # e.g., "qemu-system-x86_64", "qemu-system-arm"

    print(f"\n[INFO] [GENERIC CLEANUP] Killing lingering {qemu_bin} tasks...")
    os.system(f"pkill -9 -f {qemu_bin} 2>/dev/null")

    vm = QEMUVirtualMachine()

    try:
        print("\n[STAGE 1] Booting hypervisor engine with pure subprocess wrapper...")
        boot_success = vm.start(kernel_path=kernel_path, profile_name=profile_name)
        assert boot_success is True

        print("\n=================== RECONSTRUCTED RUNNING CMD ===================")
        print(f"{vm.binary} " + " ".join(vm.args))
        print("=================================================================\n")

        # Allow the dynamic MCP_QEMU_HOST interface to initialize completely
        time.sleep(1.0)

        print("[STAGE 2] Querying hardware telemetry status over raw QMP socket...")
        vm_status = vm.status()
        print(f" -> Live Status Response Matrix: {vm_status}")

        assert vm_status["status"] == "RUNNING"
        assert vm_status["arch"].lower() == arch_info['arch'].lower()

    finally:
        print("[STAGE 3] Invoking clean hardware shutdown sequence...")
        assert vm.stop() is True

