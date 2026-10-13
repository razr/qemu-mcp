# src/qemu_mcp/qemu/telnet_console.py
"""Optional telnet transport to a VxWorks target shell.

The serial console (QEMUConsole) is always available and carries boot messages,
EDR fault dumps and RTP stdout — but it is noisy and shared. A telnet session
gives a clean, dedicated interactive shell once the network is up and telnetd has
been started on the target (e.g. `C ipcom_telnetd` over the serial console).

This class mirrors the QEMUConsole interface (send / read_available / wait_until /
send_and_wait) so the VxWorks runtime can use either transport interchangeably.
"""
import socket
import time
import logging

logger = logging.getLogger("qemu_mcp.qemu.telnet")

# Minimal telnet IAC negotiation handling: we refuse all DO/WILL options so the
# server stops negotiating and gives us a raw line-mode shell.
IAC = 255
DONT, DO, WONT, WILL = 254, 253, 252, 251
SB, SE = 250, 240


class TelnetConsole:
    def __init__(self, host: str = "192.168.200.1", port: int = 23, connect_timeout: float = 10.0):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.sock = None

    # ------------------------------------------------------------------ connect
    def connect(self, retries: int = 20, delay: float = 1.0) -> bool:
        """Connect to the target telnet port, retrying while telnetd comes up."""
        for _ in range(retries):
            try:
                s = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
                s.settimeout(0.3)
                self.sock = s
                # read + answer the initial IAC negotiation burst
                time.sleep(0.3)
                self._drain_negotiation()
                return True
            except (ConnectionRefusedError, OSError, socket.timeout):
                time.sleep(delay)
        logger.error("telnet: could not connect to %s:%s", self.host, self.port)
        return False

    def _drain_negotiation(self):
        """Answer IAC DO/WILL with WONT/DONT so the server drops into line mode."""
        if not self.sock:
            return
        try:
            data = self.sock.recv(4096)
        except (socket.timeout, BlockingIOError):
            return
        if not data:
            return
        reply = bytearray()
        i = 0
        while i < len(data):
            if data[i] == IAC and i + 2 < len(data):
                cmd, opt = data[i + 1], data[i + 2]
                if cmd == DO:
                    reply += bytes([IAC, WONT, opt])
                elif cmd == WILL:
                    reply += bytes([IAC, DONT, opt])
                i += 3
            else:
                i += 1
        if reply:
            try:
                self.sock.sendall(bytes(reply))
            except OSError:
                pass

    # --------------------------------------------------------------- transport
    def send(self, data: str) -> bool:
        if not self.sock and not self.connect():
            return False
        payload = data if data.endswith("\n") else data + "\n"
        try:
            self.sock.sendall(payload.encode("utf-8"))
            return True
        except OSError as e:
            logger.error("telnet send failed: %s", e)
            self.sock = None
            return False

    def read_available(self) -> str:
        if not self.sock:
            return ""
        chunks = []
        while True:
            try:
                b = self.sock.recv(4096)
                if not b:
                    self.sock.close()
                    self.sock = None
                    break
                # strip IAC sequences from the stream
                chunks.append(self._strip_iac(b))
            except (socket.timeout, BlockingIOError):
                break
            except OSError:
                self.sock = None
                break
        return "".join(chunks)

    @staticmethod
    def _strip_iac(data: bytes) -> str:
        out = bytearray()
        i = 0
        while i < len(data):
            if data[i] == IAC and i + 1 < len(data):
                # skip 3-byte IAC cmd (DO/DONT/WILL/WONT) or 2-byte
                if data[i + 1] in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                    i += 3
                else:
                    i += 2
            else:
                out.append(data[i])
                i += 1
        return out.decode("utf-8", errors="ignore")

    # ----------------------------------------------------------- expect helpers
    def wait_until(self, markers, timeout: float = 30.0, poll: float = 0.3):
        if isinstance(markers, str):
            markers = [markers]
        if not self.sock and not self.connect():
            return None, ""
        acc = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self.read_available()
            if chunk:
                acc.append(chunk)
                combined = "".join(acc)
                for m in markers:
                    if m in combined:
                        return m, combined
            else:
                time.sleep(poll)
        return None, "".join(acc)

    def send_and_wait(self, command: str, markers, timeout: float = 30.0, settle: float = 0.3):
        if not self.sock and not self.connect():
            raise ConnectionError("telnet transport unreachable")
        self.read_available()  # flush stale
        self.send(command)
        if settle:
            time.sleep(settle)
        return self.wait_until(markers, timeout=timeout)[1]

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
