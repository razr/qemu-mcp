# src/qemu_mcp/qemu/profile.py
import os
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

    # Diskless kernel + a USB-FAT disk for carrying standalone programs/libraries.
    # Same diskless boot and user-mode networking as vxworks_x86_64_default, but a
    # raw FAT image is attached as a USB mass-storage device (appears on the target
    # as /bd0a). Use this to run standalone apps (e.g. a Fast-DDS example built
    # outside the ROS2 image) without tap0 or the full ros2.img: mcopy/app_upload
    # the binary + its .so deps into the image, then run /bd0a/<prog>.
    # The image path is supplied at start() time via `drive_image` -> {drive_image}.
    "vxworks_x86_64_usb": {
        "os": "vxworks",
        "arch": "x86_64",
        "qemu_bin": "qemu-system-x86_64",
        "memory": "2G",
        "platform_args": ["-cpu", "Nehalem", "-smp", "4", "-enable-kvm"],
        "network_args": [
            "-net", "nic",
            "-net", "user,hostfwd=tcp::1534-:1534,hostfwd=tcp::2345-:2345",
        ],
        "drive_args": [
            "-usb",
            "-device", "usb-ehci,id=ehci",
            "-device", "usb-storage,drive=fat32",
            "-drive", "file={drive_image},id=fat32,format=raw,if=none",
        ],
        "append_args": "bootline:fs(0,0)host:vxWorks h=10.0.2.2 e=10.0.2.15 u=target pw=vxTarget o=gei0",
        "boot_ready_markers": ["Done executing startup script", "VxWorks login", "->"],
        "kernel_shell_prompt": "->",
        "command_shell_prompt": "[vxWorks",
    },

    # Generic VxWorks x86_64 disk-image profile. Boots a VxWorks kernel and attaches a
    # raw FAT disk image (programs are mcopy'd into ::/bin, read from /bin on target):
    #   qemu-system-x86_64 -m 2G -machine q35 -cpu Nehalem
    #     -kernel <vxWorks>
    #     -net nic -net tap,ifname=tap0,script=no,downscript=no   (tap0 must pre-exist)
    #     -display none
    #     -append "<bootline>"
    #     -device ich9-ahci,id=ahci
    #     -drive file=<image>,if=none,id=vxdisk,format=raw
    #     -device ide-hd,drive=vxdisk,bus=ahci.0
    #
    # The disk image path is NOT hardcoded: it is supplied at start() time via the
    # `drive_image` argument and substituted into {drive_image}. The bootline below is
    # a sane default (host 192.168.200.254 / target 192.168.200.1, matching the tap0
    # setup in the README); override per deployment as needed. TCG (no -enable-kvm).
    "vxworks_x86_64_disk": {
        "os": "vxworks",
        "arch": "x86_64",
        "qemu_bin": "qemu-system-x86_64",
        "memory": "2G",
        "platform_args": ["-machine", "q35", "-cpu", "Nehalem"],
        "network_args": [
            "-net", "nic",
            "-net", "tap,ifname=tap0,script=no,downscript=no",
        ],
        # {drive_image} is substituted with the real image path at start() time.
        "drive_args": [
            "-device", "ich9-ahci,id=ahci",
            "-drive", "file={drive_image},if=none,id=vxdisk,format=raw",
            "-device", "ide-hd,drive=vxdisk,bus=ahci.0",
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

    # KVM-accelerated variant of the x86_64 disk profile. Faster for CPU-heavy
    # targets. Requires /dev/kvm rw + membership in the kvm group. Uses -cpu host
    # (KVM passthrough) + -smp 4. If KVM is unavailable, use vxworks_x86_64_disk (TCG).
    "vxworks_x86_64_disk_kvm": {
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
            "-drive", "file={drive_image},if=none,id=vxdisk,format=raw",
            "-device", "ide-hd,drive=vxdisk,bus=ahci.0",
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

    # Generic VxWorks raspberry-pi-4b (aarch64) disk profile. Boots the uVxWorks
    # kernel on a QEMU built from upstream master + patchwork series 515505
    # (raspi4b PCIe+GENET) + the SD-to-emmc2 routing patch, and attaches a raw FAT
    # disk image as the SD card (the VxWorks BSP drives emmc2 -> card shows as /sd0):
    #   qemu-system-aarch64 -M raspi4b -smp 4 -m 2G
    #     -kernel <uVxWorks> -dtb <dt.dtb>
    #     -nic user,model=bcm2838-genet
    #     -sd <image>
    # See knowledge/vxworks_docs/board/raspi4/qemu.md (in the apr repo) for how to
    # build this QEMU and the required patch. Override QEMU_RASPI4_BIN / _DTB env to
    # point at your local build + device tree.
    # Generic VxWorks raspberry-pi-4b (aarch64) disk profile. Boots the uVxWorks
    # kernel on a QEMU that has the BCM2838 GENET model + the SD-to-emmc2 routing
    # patch (e.g. razr/qemu branch genet-rebased-sd), attaches a raw FAT image as
    # the SD card (VxWorks BSP drives emmc2 -> /sd0), and passes the VxWorks boot
    # line via -append (-> dtb /chosen/bootargs -> vxFdtBootargsGet, same as x86),
    # so the STOCK SDK dtb is used unmodified:
    #   qemu-system-aarch64 -M raspi4b -smp 4 -m 2G
    #     -kernel <uVxWorks> -dtb <stock rpi-4b.dtb>
    #     -append "fs(0,0)...s=/sd0/vxscript"
    #     -nic tap,ifname=tap0,model=bcm2838-genet,script=no,downscript=no
    #     -sd <image>
    # A stock qemu-system-aarch64 lacks the GENET+SD patches: set QEMU_RASPI4_BIN to
    # the patched build. Set QEMU_RASPI4_DTB to the stock SDK rpi-4b.dtb (in the
    # BSP dir next to uVxWorks). See knowledge/vxworks_docs/board/raspi4/qemu.md and
    # razr/VxDocs qemu/raspberrypi/vxworks.md.
    "vxworks_raspi4_disk": {
        "os": "vxworks",
        "arch": "aarch64",
        "qemu_bin": os.environ.get(
            "QEMU_RASPI4_BIN", "qemu-system-aarch64"
        ),
        "memory": "2G",
        "platform_args": [
            "-M", "raspi4b", "-smp", "4",
            "-dtb", os.environ.get(
                "QEMU_RASPI4_DTB",
                os.path.expanduser(
                    "~/Downloads/wrsdk-vxworks7-raspberrypi4b-1.9.0/vxsdk/bsps/rpi_4_0_1_3_0/rpi-4b.dtb"
                ),
            ),
            # VxWorks on raspi4b prints on the PL011 (serial1), not the mini-UART
            # (serial0). vm.py wires the console socket as the FIRST -serial, so we
            # park a null device on serial0 here; the console chardev then lands on
            # serial1 where the dtb's stdout-path points. Without this the MCP
            # console socket gets no output and boot-ready is never detected.
            "-serial", "null",
        ],
        # tap0 for real host<->target L2 (ping / ROS2 pub/sub). host tap0 = .254,
        # target static .1 (applied by vxscript after killing the DHCP client).
        "network_args": [
            "-nic", "tap,ifname=tap0,model=bcm2838-genet,script=no,downscript=no",
        ],
        # raspi4 SD slot: attach the raw FAT image as the SD card.
        "drive_args": ["-sd", "{drive_image}"],
        # Boot line via -append (works on raspi4: QEMU writes it to /chosen/bootargs,
        # VxWorks reads it via vxFdtBootargsGet). fs(0,0)=boot from SD;
        # 192.168.200.x=tap0 subnet; f=0x0=static; s=/sd0/vxscript=run startup script.
        # MUST stay a single line.
        "append_args": (
            "fs(0,0)host:vxWorks h=192.168.200.254 e=192.168.200.1:ffffff00 "
            "g=192.168.200.254 u=target pw=vxTarget o=genet0 f=0x0 s=/sd0/vxscript"
        ),
        "boot_ready_markers": ["Done executing startup script", "->"],
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
