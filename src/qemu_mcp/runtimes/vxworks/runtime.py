# src/qemu_mcp/runtimes/vxworks/runtime.py
import time
import re
import logging
from typing import List, Dict, Any, Optional
from ..base import TargetRuntime

logger = logging.getLogger("qemu_mcp.runtimes.vxworks")

# VxWorks has two shells reachable over the same serial console:
#   ->          the C / kernel shell (default right after boot)
#   [vxWorks *]# the command (cmd) shell  <-- entered with "cmd"
#
# MODEL (per project convention): we enter the *command shell once* after boot and
# STAY there as the working shell. RTPs are launched by path (e.g. /usr/bin/foo).
# When a C/kernel routine is needed (edrShow, taskShow, rtpShow, ...), we do NOT
# switch shells — we run it from the command shell with the "C <routine>" prefix.
# This avoids fragile shell-mode toggling.

CMD_PROMPT = "[vxWorks"            # command-shell prompt fragment
KERNEL_PROMPT = "->"               # C/kernel-shell prompt

# RTP launch outcome markers
LAUNCHED_RE = re.compile(r"\(process Id = (0x[0-9a-fA-F]+)\) launched", re.I)
INSTANTIATE_FAIL = "S_rtpLib_INSTANTIATE_FAILED"
SIGNAL_RE = re.compile(r"has been deleted due to signal (\d+)", re.I)


class VxWorksRuntime(TargetRuntime):
    """VxWorks target runtime driven over the serial console.

    Operates from the command shell; reaches kernel routines via the `C` prefix.
    """

    os_name = "vxworks"

    def __init__(self, vm_backend):
        super().__init__(vm_backend)
        self._in_cmd_shell = False
        self.telnet = None            # optional TelnetConsole (clean interactive shell)
        self._telnet_in_cmd = False

    # ------------------------------------------------------------- transports
    def connect_telnet(self, host: str = "192.168.200.1", port: int = 23,
                       retries: int = 20) -> bool:
        """Open a telnet shell to the target (telnetd runs by default on many VxWorks images).

        Telnet is a clean, dedicated shell channel; the serial console stays as the
        boot/EDR/crash channel. Once connected, interactive commands route here.
        """
        from qemu_mcp.qemu.telnet_console import TelnetConsole
        tn = TelnetConsole(host=host, port=port)
        if not tn.connect(retries=retries):
            self.telnet = None
            return False
        self.telnet = tn
        self._telnet_in_cmd = False
        return True

    @property
    def _shell(self):
        """The active interactive transport: telnet if connected, else serial."""
        if self.telnet is not None and self.telnet.sock is not None:
            return self.telnet
        return self._console

    @property
    def _on_telnet(self) -> bool:
        return self.telnet is not None and self.telnet.sock is not None

    # ------------------------------------------------------------------ helpers
    @property
    def _console(self):
        if not self.vm or not self.vm.console:
            from qemu_mcp.qemu.console import QEMUConsole
            if self.vm:
                self.vm.console = QEMUConsole(self.vm)
        if not self.vm or not self.vm.console:
            raise RuntimeError("Hypervisor console channel is offline.")
        return self.vm.console

    def _prompts(self):
        prof = getattr(self.vm, "profile", None)
        cmd = getattr(prof, "command_shell_prompt", CMD_PROMPT) if prof else CMD_PROMPT
        kern = getattr(prof, "kernel_shell_prompt", KERNEL_PROMPT) if prof else KERNEL_PROMPT
        return cmd, kern

    def enter_command_shell(self, timeout: float = 30.0) -> bool:
        """Enter the VxWorks command shell on the active transport.

        On telnet the login may land directly in a shell; on serial we start at `->`.
        In both cases we send `cmd` and require the command-shell prompt. Idempotent.
        """
        cmd_prompt, kernel_prompt = self._prompts()
        shell = self._shell
        on_telnet = self._on_telnet
        if (on_telnet and self._telnet_in_cmd) or (not on_telnet and self._in_cmd_shell):
            return True
        shell.send("\r")
        matched, _ = shell.wait_until([cmd_prompt, kernel_prompt], timeout=timeout)
        if matched == cmd_prompt:
            self._set_cmd_flag(on_telnet, True)
            return True
        text = shell.send_and_wait("cmd", [cmd_prompt], timeout=timeout, settle=0.3)
        ok = cmd_prompt in text
        self._set_cmd_flag(on_telnet, ok)
        return ok

    def _set_cmd_flag(self, on_telnet: bool, value: bool):
        if on_telnet:
            self._telnet_in_cmd = value
        else:
            self._in_cmd_shell = value

    def _ensure_cmd(self):
        on_telnet = self._on_telnet
        in_cmd = self._telnet_in_cmd if on_telnet else self._in_cmd_shell
        if not in_cmd:
            self.enter_command_shell()

    # ----------------------------------------------------------------- contract
    def run_shell_command(self, command: str, timeout: float = 5.0) -> str:
        """Run a command in the VxWorks command shell (telnet if available)."""
        self._ensure_cmd()
        cmd_prompt, _ = self._prompts()
        try:
            return self._shell.send_and_wait(command, [cmd_prompt], timeout=timeout)
        except Exception as e:
            return f"Exception during console exchange: {e}"

    def run_kernel_routine(self, routine: str, timeout: float = 15.0) -> str:
        """Run a C/kernel-shell routine (e.g. 'edrShow') from the command shell.

        Uses the `C <routine>` prefix so no shell switch is needed. Routed through
        the active interactive transport (telnet if connected).
        """
        self._ensure_cmd()
        cmd_prompt, _ = self._prompts()
        return self._shell.send_and_wait(f"C {routine}", [cmd_prompt], timeout=timeout)

    def upload(self, host_path: str, remote_path: str) -> bool:
        """Deploy a file into the FAT image.

        For disk profiles the drive image is a raw FAT partition; we write with
        mtools (mcopy) which is reliable (fusefat `cp` corrupts files mid-write).
        Requires the VM to be stopped (exclusive access to the image file).
        """
        import os
        import subprocess
        img = getattr(self.vm, "drive_image", None)
        if not img or not os.path.exists(img):
            logger.error("upload: no disk image bound to this VM (drive_image unset).")
            return False
        name = os.path.basename(remote_path)
        dest = "::/bin/" + name
        try:
            subprocess.run(["mdel", "-i", img, dest], capture_output=True)
            r = subprocess.run(
                ["mcopy", "-i", img, "-D", "o", host_path, dest],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                logger.error("mcopy failed: %s", r.stderr.strip())
                return False
            # verify byte-exact: size must appear, and the file's 8.3 short name.
            # mdir prints 8.3 as "<base up to 8>  <ext>" (space-separated, no dot),
            # so match on the dot-less basename (NOT name[:8], which can include the
            # dot for short names like 'hello.vxe' and never matches).
            chk = subprocess.run(["mdir", "-i", img, "::/bin"], capture_output=True, text=True)
            want = str(os.path.getsize(host_path))
            base = os.path.splitext(name)[0].lower()[:8]
            return want in chk.stdout and base in chk.stdout.lower()
        except FileNotFoundError:
            logger.error("upload: mtools (mcopy/mdir) not installed on host.")
            return False

    def exec(self, path: str, args: List[str], options: Dict[str, Any]) -> str:
        """Launch an RTP by path and classify the outcome (short form)."""
        return self.exec_detailed(path, args, options)["_short"]

    def _collect_outcome_text(self, launch: str, options: Dict[str, Any]) -> str:
        """Send a launch command on the active shell and gather outcome text from
        BOTH transports — the crash line ('deleted due to signal') and RTP stdout
        print to the SERIAL console even when the command was issued over telnet."""
        cmd_prompt, _ = self._prompts()
        shell = self._shell
        serial = self._console
        markers = [INSTANTIATE_FAIL, "has been deleted due to signal", "launched"]
        # flush both
        shell.read_available()
        if shell is not serial:
            serial.read_available()
        shell.send(launch)
        time.sleep(0.3)

        text = ""
        deadline = time.time() + options.get("timeout", 30.0)
        done = False
        while time.time() < deadline and not done:
            text += shell.read_available()
            if shell is not serial:
                text += serial.read_available()
            if INSTANTIATE_FAIL in text or "has been deleted due to signal" in text:
                done = True
            time.sleep(0.25)
        # brief post-drain to catch a crash that follows the launch line
        post_deadline = time.time() + options.get("post_timeout", 8.0)
        while time.time() < post_deadline:
            more = shell.read_available()
            if shell is not serial:
                more += serial.read_available()
            text += more
            if "has been deleted due to signal" in text or INSTANTIATE_FAIL in text:
                break
            if not more:
                time.sleep(0.25)
        return text

    def exec_detailed(self, path: str, args: List[str], options: Dict[str, Any]) -> Dict[str, Any]:
        """Launch an RTP by path and return a classified outcome + raw console text.

        outcome: LAUNCHED (+rtp_id) | INSTANTIATE_FAILED | SIGNAL_<n> | NO_LAUNCH.
        options: stack_size (hex str) raises rtpSpStackSize first; timeout/post_timeout.
        """
        self._ensure_cmd()
        cmd_prompt, _ = self._prompts()
        stack = options.get("stack_size")
        if stack:
            self._shell.send_and_wait(f"C rtpSpStackSize={stack}", [cmd_prompt], timeout=10)
        arg_str = " ".join(args) if args else ""
        launch = f"{path} {arg_str}".strip()

        text = self._collect_outcome_text(launch, options)

        outcome = "NO_LAUNCH"
        rtp_id = None
        signal_num = None
        if INSTANTIATE_FAIL in text:
            outcome = "INSTANTIATE_FAILED"
        elif SIGNAL_RE.search(text):
            signal_num = int(SIGNAL_RE.search(text).group(1))
            outcome = f"SIGNAL_{signal_num}"
        elif LAUNCHED_RE.search(text):
            rtp_id = LAUNCHED_RE.search(text).group(1)
            outcome = "LAUNCHED"
        return {
            "path": path,
            "outcome": outcome,
            "rtp_id": rtp_id,
            "signal": signal_num,
            "raw_output": text,
            # short form for exec(): rtp id on success else the outcome token
            "_short": rtp_id if outcome == "LAUNCHED" else outcome,
        }

    def kill(self, target_id: str) -> bool:
        """Terminate an RTP via the kernel routine rtpDelete."""
        self.run_kernel_routine(f"rtpDelete {target_id}")
        return True

    def status(self, target_id: str) -> Dict[str, Any]:
        """Query an RTP via the kernel routine rtpShow."""
        output = self.run_kernel_routine(f"rtpShow {target_id}")
        is_alive = any(s in output for s in ("STATE_READY", "STATE_NORMAL", "RUNNING"))
        state = "RUNNING" if is_alive else "STOPPED"
        if "ZOMBIE" in output:
            state = "ZOMBIE"
        return {
            "target_id": target_id,
            "is_alive": is_alive,
            "state": state,
            "raw_output": output,
        }

    def fetch_logs(self, target_id: str, tail_lines: int = 100) -> str:
        """RTP stdout is on the shared serial console; there is no per-RTP log file.

        Return the recently buffered console text as a best-effort.
        """
        return self._console.read_available()

    def inspect(self, mode: str) -> Dict[str, Any]:
        """Global diagnostics via kernel routines (run with the C prefix)."""
        cmd_map = {
            "tasks": "i",          # task summary
            "memory": "memShow",
            "fds": "iosFdShow",
            "edr": "edrShow",
        }
        if mode not in cmd_map:
            raise ValueError(f"Unsupported inspect mode: {mode} (have {list(cmd_map)})")
        raw = self.run_kernel_routine(cmd_map[mode])
        return {"mode": mode, "raw_output": raw}

    # ------------------------------------------------------------ EDR / faults
    def edr_show(self, timeout: float = 20.0) -> Dict[str, Any]:
        """Dump the EDR fatal record and parse the PC + fault/access address.

        Returns {raw_output, pc, access_address, exception, task, has_record}.
        """
        raw = self.run_kernel_routine("edrShow", timeout=timeout)
        return self._parse_edr(raw)

    @staticmethod
    def _parse_edr(raw: str) -> Dict[str, Any]:
        def grab(patterns):
            for pat in patterns:
                m = re.search(pat, raw, re.I)
                if m:
                    return m.group(1).strip()
            return None

        pc = grab([
            r"Program Counter\s*[:=]\s*(0x[0-9a-fA-F]+)",
            r"\bpc\s*=\s*(0x[0-9a-fA-F]+)",       # register-dump format: "pc = 0x..."
            r"\brip\s*[:=]\s*(0x[0-9a-fA-F]+)",
        ])
        access = grab([
            r"Access Address\s*[:=]\s*(0x[0-9a-fA-F]+)",
            r"Fault Address\s*[:=]\s*(0x[0-9a-fA-F]+)",
            r"Faulting Address\s*[:=]\s*(0x[0-9a-fA-F]+)",
            r"\bcr2\s*=?\s*[:=]?\s*(0x[0-9a-fA-F]+)",
        ])
        exc = grab([
            r"Exception\s*[:=]?\s*(.+)",
            r"Trap\s*[:=]?\s*(.+)",
            r"vector\s*[:=]\s*(0x[0-9a-fA-F]+)",
        ])
        task = grab([
            r"Task\s*[:=]\s*(\S+)",
            r"Faulting task\s*[:=]\s*(\S+)",
            r"RTP\s*[:=]\s*(\S+)",
        ])
        # Registers block (useful context for the agent)
        regs = {}
        for rm in re.finditer(r"\b(r[a-z0-9]+|pc|eflags|tlsbase)\s*=\s*(0x[0-9a-fA-F]+)", raw):
            regs[rm.group(1)] = rm.group(2)

        has_record = (
            bool(pc or access)
            or "<<<<<Traceback>>>>>" in raw
            or "INJECT" in raw.upper()
            or "FATAL" in raw.upper()
        )

        # Classify the fault per the PC/access-address relationship.
        classification = None
        try:
            pc_i = int(pc, 16) if pc else None
            acc_i = int(access, 16) if access else None
            if pc_i == 0:
                classification = "NULL_PC_jumped_to_address_0 (call through NULL/invalid function pointer)"
            elif pc_i is not None and acc_i is not None and pc_i == acc_i:
                classification = "PC==fault_addr (executed an invalid/corrupt code pointer)"
            elif acc_i is not None and acc_i <= 0x200:
                classification = "near-NULL data access (NULL pointer / offset-from-NULL deref)"
            elif acc_i is not None and acc_i >= 0x10000000:
                classification = "high/unmapped address access"
        except (ValueError, TypeError):
            pass

        return {
            "raw_output": raw,
            "pc": pc,
            "access_address": access,
            "exception": exc,
            "task": task,
            "registers": regs,
            "classification": classification,
            "has_record": has_record,
        }
