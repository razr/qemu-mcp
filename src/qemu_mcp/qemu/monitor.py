# src/qemu_mcp/qemu/monitor.py
import socket
import json
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("qemu_mcp.qemu.monitor")

class QEMUMonitor:
    """
    Handles native QEMU Machine Protocol (QMP) interactions over TCP loopback channels.
    Provides on-demand self-healing connectivity to survive stateless life cycles.
    """
    def __init__(self, host: Optional[str] = None, port: int = 15556):
        self.host = host or os.getenv("MCP_QEMU_HOST", "127.0.0.1")
        self.port = port
        self.sock: Optional[socket.socket] = None

    def connect(self, retries: int = 5) -> bool:
        """Establishes connection to the QMP socket server and executes the capabilities handshake."""
        self.disconnect()
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(1.0)

            for _ in range(retries):
                try:
                    self.sock.connect((self.host, self.port))
                    break
                except (ConnectionRefusedError, socket.timeout):
                    time.sleep(0.1)
            else:
                raise ConnectionRefusedError(f"Could not connect to QMP server at {self.host}:{self.port}")

            # A. Read initial greeting capability negotiation banner
            _ = self.sock.recv(4096)

            # B. Execute capabilities handshake command
            negotiate_cmd = json.dumps({"execute": "qmp_capabilities"}) + "\n"
            self.sock.sendall(negotiate_cmd.encode("utf-8"))

            # C. Read execution acknowledgment
            _ = self.sock.recv(4096)

            self.sock.settimeout(0.5)
            return True
        except Exception as e:
            logger.error(f"Failed to initialize QMP handshake loop: {e}")
            self.disconnect()
            return False

    def execute(self, command: str, arguments: Optional[dict] = None) -> Dict[str, Any]:
        """Executes a JSON-RPC payload. Connects automatically if the socket is closed."""
        is_temporary = False
        if not self.sock:
            if not self.connect(retries=1):
                return {"error": "QMP server unreachable"}
            is_temporary = True

        try:
            payload: Dict[str, Any] = {"execute": command}
            if arguments:
                payload["arguments"] = arguments

            cmd_str = json.dumps(payload) + "\n"
            self.sock.sendall(cmd_str.encode("utf-8"))

            response_bytes = self.sock.recv(4096)
            return json.loads(response_bytes.decode("utf-8"))
        except Exception as e:
            self.disconnect()
            return {"error": str(e)}
        finally:
            if is_temporary:
                self.disconnect()

    def disconnect(self):
        """Safely tears down the active socket channel."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

