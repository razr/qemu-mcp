# tests/test_console.py
import time
import pytest
from unittest.mock import MagicMock
from qemu_mcp.qemu.console import QEMUConsole

def test_live_qemu_serial_interaction():
    """
    Connects directly to the live running QEMU instance on port 15555,
    drains the boot logs, sends a newline, and reads the real VxWorks prompt.
    """
    # 1. Instantiate the minimal wrapper object required by the new console logic
    mock_vm = MagicMock()

    # 2. Stub the raw process wrapper handle to simulate a healthy running backend
    mock_vm._process = MagicMock()
    mock_vm._process.poll.return_value = None  # None indicates the process is still running

    # Connect directly to your live running QEMU process on port 15555
    console = QEMUConsole(mock_vm)

    print("\n[STAGE 1] Connecting to port 15555 and draining current buffer...")
    boot_logs = console.read_available()
    print("------------------ CAPTURED LIVE LOGS ------------------")
    print(boot_logs or "(Log buffer was already cleared)")
    print("--------------------------------------------------------")

    print("[STAGE 2] Sending newline down the wire to awake shell...")
    assert console.send("\n") is True
    time.sleep(0.2)  # Short propagation wait for the TCP socket stream

    prompt_check = console.read_available()
    print(f" -> Shell Response Fragment: {repr(prompt_check)}")

    # Assert that the real target returned the true VxWorks prompt
    assert "->" in prompt_check, f"Expected VxWorks prompt '->', got: {repr(prompt_check)}"
    print("[SUCCESS] Successfully read real serial bytes from the running QEMU instance.")

