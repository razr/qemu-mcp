# src/qemu_mcp/qemu/console.py
import logging
import socket
import select
import time

logger = logging.getLogger("qemu_mcp.qemu")

class QEMUConsole:
    """
    Interactive Console Interface for the QEMU Backend Layer.
    Connects directly over the explicitly provisioned localhost serial socket pipeline.
    """
    def __init__(self, vm_object):
        self.vm_object = vm_object
        self.sock = None

    def _connect_socket(self) -> bool:
        """Establishes connection to the QEMU serial socket using a safe handshake."""
        if self.sock:
            return True
        try:
            # Create a standard TCP Socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # --- FIX: USE BLOCKING CONNECT TO ENSURE SOCKET IS IMMEDIATELY PRIMED ---
            # This replicates the exact behavior of manual 'nc' execution
            self.sock.settimeout(1.0)

            for attempt in range(5):
                try:
                    self.sock.connect(("127.0.0.1", 15555))
                    # Once connection is confirmed, flip it back to non-blocking mode
                    # for our safe runtime selection polling
                    self.sock.setblocking(False)
                    return True
                except (ConnectionRefusedError, socket.timeout):
                    time.sleep(0.2)

            logger.error("Console socket connection timed out after 5 attempts.")
            self.sock = None
            return False
        except Exception as e:
            logger.error(f"Failed to bind to local console socket matrix: {e}")
            self.sock = None
            return False

    def send(self, data: str) -> bool:
        """Pushes an encoded text string down the serial socket."""
        if not self.vm_object or not self.vm_object._process or self.vm_object._process.poll() is not None:
            return False
        try:
            if self._connect_socket():
                self.sock.sendall(data.encode("utf-8"))
                return True
            return False
        except Exception:
            return False

    def read_available(self) -> str:
        """Drains all currently unread characters from the console socket dynamically."""
        if not self.vm_object or not self.vm_object._process or self.vm_object._process.poll() is not None:
            return ""

        output_chunks = []
        try:
            while True:
                # Direct non-blocking select over the primed socket
                ready, _, _ = select.select([self.sock], [], [], 0.0)
                if not ready:
                    break

                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                output_chunks.append(chunk)
        except Exception:
            pass

        if not output_chunks:
            return ""

        return b"".join(output_chunks).decode("utf-8", errors="ignore")

