# tests/test_qemu_stateless_lifecycle.py
import os
import time
import pytest

from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.runtimes.detector import get_arch_info
from qemu_mcp.qemu.profile import QEMUProfile

def test_qemu_vxworks_stateless_lifecycle(kernel_path):
    """
    Validates that status and stop work correctly across completely
    isolated object instances, mimicking FastMCP's stateless behavior.
    """
    if not kernel_path:
        pytest.fail("Error: You must provide a path to a real kernel using: --kernel-path=<path>")

    if not os.path.exists(kernel_path):
        raise FileNotFoundError(f"Provided kernel file not found at: '{kernel_path}'")

    # 1. Dynamically discover the architecture and binary target name
    arch_info = get_arch_info(kernel_path)
    detected_arch = arch_info["arch"]
    profile_name = f"vxworks_{detected_arch}_default"

    profile = QEMUProfile(log_path="qemu_vms.log", profile_name=profile_name)
    qemu_bin = os.path.basename(profile.qemu_bin) # e.g., "qemu-system-x86_64" or "qemu-system-arm"

    print(f"\n[INFO] [STATELESS TEST] Detected Binary: {qemu_bin} for Profile: {profile_name}")

    # Ensure no leftover processes for this specific architecture are running
    os.system(f"pkill -9 -f {qemu_bin} 2>/dev/null")

    try:
        # --- PHASE 1: START IN INSTANCE A ---
        print("[STATELESS STAGE 1] Launching QEMU in Instance A...")
        vm_a = QEMUVirtualMachine()
        vm_a.start(kernel_path=kernel_path, profile_name=profile_name)
        time.sleep(0.5)

        # Simulate FastMCP tool ending: destroy Instance A completely
        del vm_a
        print("[STATELESS STAGE 1.5] Instance A completely destroyed from memory.")

        # --- PHASE 2: QUERY STATUS IN INSTANCE B ---
        print("[STATELESS STAGE 2] Querying status using a brand-new Instance B...")
        vm_b = QEMUVirtualMachine()
        vm_status = vm_b.status()
        print(f" -> Retrieved Status Matrix from Instance B: {vm_status}")

        # This assertion will FAIL on your current code (it returns "STOPPED")
        assert vm_status["status"] == "RUNNING"
        del vm_b

    except (QEMUMachineError, Exception) as e:
        print(f"\n[STATELESS FAILURE] Exception encountered: {e}")
        # Emergency cleanup using the dynamic binary name
        os.system(f"pkill -9 -f {qemu_bin} 2>/dev/null")
        pytest.fail(f"Stateless validation failed: {e}")

    finally:
        # --- PHASE 3: SHUTDOWN IN INSTANCE C ---
        print("[STATELESS STAGE 3] Triggering shutdown via a brand-new Instance C...")
        vm_c = QEMUVirtualMachine()
        vm_c.stop(binary_name=qemu_bin)
        del vm_c

        # Verify QEMU process actually terminated on the Linux OS level
        time.sleep(0.5)

        # CRITICAL FIX: Change "-f" to "-x" in the test assertion block!
        process_still_exists = os.system(f"pgrep -x {qemu_bin} > /dev/null") == 0

        if process_still_exists:
            print(f"[❌ STATELESS FAILURE] {qemu_bin} process is still hanging in the background!")
            os.system(f"pkill -9 -x {qemu_bin} 2>/dev/null")
            pytest.fail("Process tree failed to close across stateless instances.")
        else:
            print("[+] Process tree completely cleaned up statelessly.")

