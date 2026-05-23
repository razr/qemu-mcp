# tests/test_monitor.py
import os
import time
import pytest

from qemu_mcp.qemu.vm import QEMUVirtualMachine
from qemu_mcp.qemu.monitor import QEMUMonitor
from qemu_mcp.runtimes.detector import get_arch_info
from qemu_mcp.qemu.profile import QEMUProfile

def test_monitor_real_qmp_integration_and_stateless_commands(kernel_path):
    """
    True integration test verifying the QEMUMonitor against a live QEMU instance.
    Validates protocol negotiation, query execution frames, and stateless auto-reconnection blocks.
    """
    if not kernel_path:
        pytest.fail("Error: You must provide a path to a real kernel using: --kernel-path=<path>")

    if not os.path.exists(kernel_path):
        raise FileNotFoundError(f"Provided kernel file not found at: '{kernel_path}'")

    # 1. Resolve runtime environments dynamically
    arch_info = get_arch_info(kernel_path)
    profile_name = f"vxworks_{arch_info['arch']}_default"

    profile = QEMUProfile(log_path="qemu_vms.log", profile_name=profile_name)
    qemu_bin = os.path.basename(profile.qemu_bin)

    # 2. Hard environment cleanup before launching the target instance
    os.system(f"pkill -9 -x {qemu_bin} 2>/dev/null")

    # Force the local host target to test loopback mechanics natively
    os.environ["MCP_QEMU_HOST"] = "127.0.0.1"
    vm = QEMUVirtualMachine()

    try:
        print("\n[MONITOR INTEGRATION 1] Launching real QEMU background process...")
        boot_success = vm.start(kernel_path=kernel_path, profile_name=profile_name)
        assert boot_success is True

        # Give the operating system loopback socket binding sequence a moment to initialize completely
        time.sleep(1.0)

        # Ensure the orchestrator's initialization monitor channel is disconnected
        # so we can test standalone and stateless interactions
        vm.monitor.disconnect()

        # -------------------------------------------------------------------
        # TEST 1: STANDALONE EXPLICIT CONNECT & HANDSHAKE
        # -------------------------------------------------------------------
        print("[MONITOR INTEGRATION 2] Testing explicit manual connection handshake loop...")
        standalone_monitor = QEMUMonitor(host="127.0.0.1", port=15556)

        # This confirms our manual network wire handshake (Greeting banner + capabilities negotiation ACK)
        assert standalone_monitor.connect(retries=3) is True
        assert standalone_monitor.sock is not None

        print(" -> Executing status command via manual persistent socket channel...")
        status_res = standalone_monitor.execute("query-status")
        print(f" -> Response payload: {status_res}")
        assert "error" not in status_res
        assert status_res.get("return", {}).get("status") == "running"

        # Disconnect explicitly to clean up the tracker handle
        standalone_monitor.disconnect()
        assert standalone_monitor.sock is None

        # -------------------------------------------------------------------
        # TEST 2: STATELESS AUTO-RECONNECTION (MIMICKING Kiro/FastMCP LIFE CYCLES)
        # -------------------------------------------------------------------
        print("[MONITOR INTEGRATION 3] Testing stateless automatic self-healing execution channel...")
        stateless_monitor = QEMUMonitor(host="127.0.0.1", port=15556)

        # Crucial Stateless Check: Socket initialization block must start as completely empty
        assert stateless_monitor.sock is None

        print(" -> Running command via empty stateless object handle...")
        # The execute() invocation must realize the socket is empty, call connect() on-the-fly,
        # negotiate capabilities, run query-commands, and instantly close down temporary file descriptors
        stateless_res = stateless_monitor.execute("query-status")
        print(f" -> Stateless response payload: {stateless_res}")

        assert "error" not in stateless_res
        assert stateless_res.get("return", {}).get("status") == "running"

        # Verify that temporary socket allocations tear down resource links after data delivery finishes
        assert stateless_monitor.sock is None

    finally:
        print("[MONITOR INTEGRATION 4] Sending native clean QMP quit sequence...")
        # Tear down using an independent stateless closure handler
        teardown_monitor = QEMUMonitor(host="127.0.0.1", port=15556)
        quit_res = teardown_monitor.execute("quit")
        print(f" -> Teardown handshake result: {quit_res}")

        time.sleep(0.5)
        # Ensure the hypervisor process group has actually vanished from the operating system stack kernel table
        process_still_exists = os.system(f"pgrep -x {qemu_bin} > /dev/null") == 0
        if process_still_exists:
            print(f"[❌ INTEGRATION FAILURE] {qemu_bin} process failed to shut down via QMP!")
            os.system(f"pkill -9 -x {qemu_bin} 2>/dev/null")
            pytest.fail("The real hypervisor process tree leaked.")
        else:
            print("[+] Live hypervisor closed down cleanly via monitor commands.")
