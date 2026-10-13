# src/qemu_mcp/qemu/profile.py
from typing import List, Dict, Any

# Each profile fully describes a QEMU invocation for a target.
# Keys:
#   os, arch, qemu_bin            - target identity + binary
#   memory                        - -m value
#   platform_args                 - machine/cpu/smp/accel flags
#   network_args                  - -net ... flags
#   drive_args                    - block device flags (empty for diskless kernels)
#   append_args                   - the -append bootline string
#   boot_ready_markers            - console substrings that indicate the OS finished booting
#   kernel_shell_prompt           - the C/kernel shell prompt ("->")
#   command_shell_prompt          - the command shell prompt fragment ("[vxWorks")
PROFILES: Dict[str, Dict[str, Any]] = {
    # Diskless user-net profile (original) — kept for simple kernel-only boots.
    "vxworks_x86_64_default": {
        "os": "vxworks",
        "arch": "x86_64",
        "qemu_bin": "qemu-system-x86_64",
        "memory": "1G",
        "platform_args": ["-cpu", "Nehalem", "-smp", "4", "-enable-kvm"],
        "network_args": [
            "-net", "nic",
            "-net", "user,hostfwd=tcp::1534-:1534,hostfwd=tcp::2345-:2345",
        ],
        "drive_args": [],
        "append_args": "bootline:fs(0,0)host:vxWorks h=10.0.2.2 e=10.0.2.15 u=target pw=vxTarget o=gei0",
        "boot_ready_markers": ["Done executing startup script", "VxWorks login", "->"],
        "kernel_shell_prompt": "->",
        "command_shell_prompt": "[vxWorks",
    },

    # Lyrical ROS 2 disk-image profile — mirrors the proven working boot line:
    #   qemu-system-x86_64 -m 2G -machine q35 -cpu Nehalem
    #     -kernel <vxWorks>
    #     -net nic -net tap,ifname=tap0,script=no,downscript=no
    #     -display none -serial mon:stdio
    #     -append "bootline:fs(0,0)host:/vxWorks h=192.168.200.254 ... s=/ata0/vxscript"
    #     -device ich9-ahci,id=ahci
    #     -drive file=output/ros2.img,if=none,id=ros2disk,format=raw
    #     -device ide-hd,drive=ros2disk,bus=ahci.0
    #
    # NOTE: no -enable-kvm (TCG, matches the proven setup); the disk image path is
    # supplied at start() time via the `drive_image` argument and substituted into
    # drive_args by QEMUProfile.
    "vxworks_lyrical_disk": {
        "os": "vxworks",
        "arch": "x86_64",
        "qemu_bin": "qemu-system-x86_64",
        "memory": "2G",
        "platform_args": ["-machine", "q35", "-cpu", "Nehalem"],
        "network_args": [
            "-net", "nic",
            "-net", "tap,ifname=tap0,script=no,downscript=no",
        ],
        # {drive_image} is substituted with the real image path at build time.
        "drive_args": [
            "-device", "ich9-ahci,id=ahci",
            "-drive", "file={drive_image},if=none,id=ros2disk,format=raw",
            "-device", "ide-hd,drive=ros2disk,bus=ahci.0",
        ],
        "append_args": (
            "bootline:fs(0,0)host:/vxWorks "
            "h=192.168.200.254 e=192.168.200.1 g=192.168.200.254 "
            "u=ftp pw=ftp123 o=gei0 s=/ata0/vxscript"
        ),
        "boot_ready_markers": ["Done executing startup script"],
        "kernel_shell_prompt": "->",
        "command_shell_prompt": "[vxWorks",
    },

    # KVM-accelerated variant of the lyrical disk profile. ~faster for CPU-heavy
    # workloads (rclrs/DDS init). Requires /dev/kvm rw + membership in the kvm group.
    # Uses -cpu host (KVM passthrough) + -smp 4 (SDK default). Falls back is manual:
    # if KVM is unavailable, use vxworks_lyrical_disk (TCG).
    "vxworks_lyrical_disk_kvm": {
        "os": "vxworks",
        "arch": "x86_64",
        "qemu_bin": "qemu-system-x86_64",
        "memory": "2G",
        "platform_args": ["-machine", "q35", "-cpu", "host", "-smp", "4", "-enable-kvm"],
        "network_args": [
            "-net", "nic",
            "-net", "tap,ifname=tap0,script=no,downscript=no",
        ],
        "drive_args": [
            "-device", "ich9-ahci,id=ahci",
            "-drive", "file={drive_image},if=none,id=ros2disk,format=raw",
            "-device", "ide-hd,drive=ros2disk,bus=ahci.0",
        ],
        "append_args": (
            "bootline:fs(0,0)host:/vxWorks "
            "h=192.168.200.254 e=192.168.200.1 g=192.168.200.254 "
            "u=ftp pw=ftp123 o=gei0 s=/ata0/vxscript"
        ),
        "boot_ready_markers": ["Done executing startup script"],
        "kernel_shell_prompt": "->",
        "command_shell_prompt": "[vxWorks",
    },
}


class QEMUProfile:
    def __init__(self, log_path: str, profile_name: str = None):
        self.profile_name = profile_name or "vxworks_x86_64_default"
        if self.profile_name not in PROFILES:
            raise ValueError(f"Unknown configuration profile: {self.profile_name}")
        self.config = PROFILES[self.profile_name]
        self.log_path = log_path

    @property
    def qemu_bin(self) -> str:
        return self.config["qemu_bin"]

    @property
    def arch(self) -> str:
        return self.config["arch"]

    @property
    def os_name(self) -> str:
        return self.config["os"]

    @property
    def memory(self) -> str:
        return self.config.get("memory", "1G")

    def platform_args(self) -> List[str]:
        return list(self.config.get("platform_args", []))

    def network_args(self) -> List[str]:
        return list(self.config.get("network_args", []))

    def drive_args(self, drive_image: str = None) -> List[str]:
        """Return block-device args, substituting the real image path for {drive_image}.

        If the profile declares drive_args but no drive_image is provided, raises so
        we never silently boot a disk profile without its image.
        """
        raw = self.config.get("drive_args", [])
        if not raw:
            return []
        if drive_image is None:
            raise ValueError(
                f"Profile '{self.profile_name}' requires a disk image "
                f"(pass drive_image to start())."
            )
        return [a.replace("{drive_image}", drive_image) for a in raw]

    def append_args(self) -> str:
        return self.config.get("append_args", "")

    def boot_ready_markers(self) -> List[str]:
        return list(self.config.get("boot_ready_markers", ["->"]))

    @property
    def kernel_shell_prompt(self) -> str:
        return self.config.get("kernel_shell_prompt", "->")

    @property
    def command_shell_prompt(self) -> str:
        return self.config.get("command_shell_prompt", "[vxWorks")
