# src/qemu_mcp/qemu/profile.py
from typing import List, Dict, Any

PROFILES: Dict[str, Dict[str, Any]] = {
    "vxworks_x86_64_default": {
        "os": "vxworks",
        "arch": "x86_64",
        "qemu_bin": "qemu-system-x86_64",
        "platform_args": ["-cpu", "Nehalem", "-smp", "4", "-enable-kvm"],
        "network_args": [
            "-net", "nic", 
            "-net", "user,hostfwd=tcp::1534-:1534,hostfwd=tcp::2345-:2345"
        ],
        "append_args": "bootline:fs(0,0)host:vxWorks h=10.0.2.2 e=10.0.2.15 u=target pw=vxTarget o=gei0"
    }
}

class QEMUProfile:
    def __init__(self, log_path: str, profile_name: str = None):
        self.profile_name = profile_name or "vxworks_x86_64_default"
        if self.profile_name not in PROFILES:
            raise ValueError(f"Unknown configuration profile: {self.profile_name}")
        self.config = PROFILES[self.profile_name]
        self.log_path = log_path

    @property
    def qemu_bin(self) -> str: return self.config["qemu_bin"]
    @property
    def arch(self) -> str: return self.config["arch"]

    def base_args(self, kernel_path: str) -> List[str]:
        return [
            "-m", "1024M",
            "-kernel", kernel_path,
            "-display", "none",
            "-monitor", "none"
        ]

    def platform_args(self) -> List[str]: return self.config.get("platform_args", [])
    def network_args(self) -> List[str]: return self.config.get("network_args", [])
    def append_args(self) -> str: return self.config.get("append_args", "")

