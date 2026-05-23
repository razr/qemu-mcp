# src/qemu_mcp/qemu/console.py
import socket
import logging
import time

logger = logging.getLogger("qemu_mcp.qemu.console")

class QEMUConsole:
    def __init__(self, vm_object):
        self.vm_object = vm_object
        self.sock = None

    def _connect_socket(self) -> bool:
        """Establishes connection to the QEMU serial socket using a safe handshake."""
        target_host = self.vm_object.host_target if hasattr(self.vm_object, "host_target") else "127.0.0.1"
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(1.0)

            for _ in range(5):
                try:
                    self.sock.connect((target_host, 15555))
                    break
                except (ConnectionRefusedError, socket.timeout):
                    time.sleep(0.1)
            else:
                logger.error(f"Console helper failed to connect to socket interface at {target_host}:15555")
                self.sock = None
                return False

            # Set to non-blocking timeout mode for instant flushes
            self.sock.settimeout(0.1)
            return True
        except Exception as e:
            logger.error(f"Failed to bind to local console socket matrix: {e}")
            self.sock = None
            return False

    def send(self, data: str) -> bool:
        """Flushes a raw string down the connected console wire descriptor loop."""
        if not self.sock:
            if not self._connect_socket():
                return False
        try:
            self.sock.sendall(data.encode("utf-8"))
            return True
        except Exception as e:
            logger.error(f"Failed to write bytes down the active console pipe: {e}")
            self.sock = None
            return False

    def read_available(self) -> str:
        """Drains all outstanding readable text data currently pooled inside the stream buffer."""
        if not self.sock:
            if not self._connect_socket():
                return ""

        buffer_chunks = []
        while True:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    # Remote side closed connection cleanly
                    self.sock.close()
                    self.sock = None
                    break
                buffer_chunks.append(chunk.decode("utf-8", errors="ignore"))
            except (socket.timeout, BlockingIOError):
                # Timeout is normal when no data is left! Do NOT close the socket here!
                break
            except Exception as e:
                logger.error(f"Exception encountered during read trace: {e}")
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
                break

        return "".join(buffer_chunks)

    def exchange_text(self, text_payload: str, delay: float = 1.0) -> str:
        """
        Generic transport-layer method. Clears the incoming network buffer,
        transmits a text string, waits, and collects the response raw.
        """
        if not self.sock:
            if not self._connect_socket():
                raise ConnectionError("Console transport interface is completely unreachable.")

        # 1. Clear stale data sitting on the wire
        self.read_available()

        # 2. Transmit the command string
        formatted_text = text_payload if text_payload.endswith("\n") else f"{text_payload}\n"
        if not self.send(formatted_text):
            raise IOError("Failed to flush character stream down the socket pipeline.")

        # 3. Wait for the remote hardware buffer to compile response frames
        time.sleep(delay)

        # 4. Return whatever raw data came back over the wire
        return self.read_available()

