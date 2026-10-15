# QEMU MCP Server

An MCP (Model Context Protocol) server that lets an AI agent boot and drive
**QEMU** virtual machines running embedded real-time operating systems — primarily
**VxWorks** (Zephyr/others pluggable). It exposes a small, ordered set of tools to
boot a target, upload a program into its disk image, launch it, and capture
structured results (including crash/fault records).

This is a **generic VxWorks QEMU driver** — it is not tied to any particular
application stack. Project-specific values (bootline, target IP, disk image) are
passed in by the caller; sane defaults are provided.

## Agent workflow (tool ordering)

```
start_qemu(kernel_path=..., profile=..., drive_image=..., wait_boot=True)
   │   (boots QEMU, waits for the boot-ready marker, enters the command shell,
   │    and connects telnet if the target offers it)
   ├─ app_upload(host_path=..., remote_path="/bin/app.vxe")   # disk-image profiles only
   ├─ app_exec_detailed(path="/bin/app.vxe")  →  LAUNCHED | SIGNAL_<n> | INSTANTIATE_FAILED
   │       └─ on SIGNAL_11:  edr_show()        # parse the fault record (pc, access addr)
   ├─ app_fetch_logs(target_id=...)            # program output
   ├─ run_kernel_routine("taskShow")           # C/kernel-shell routines via `C <routine>`
   └─ stop_qemu()
```

Prefer **`app_exec_detailed`** over `app_exec`: it returns a classified outcome
(LAUNCHED/SIGNAL_n/INSTANTIATE_FAILED) plus raw console text, watching both the
telnet shell and the serial console (crashes print to serial even when launched
over telnet).

## Prerequisites

### Host tools
- **QEMU** (`qemu-system-x86_64`).
- **mtools** (`mcopy`, `mdir`, `mdel`, `mmd`) and **dosfstools** (`mkfs.vfat`) —
  required to build and write the FAT disk image used by disk-image profiles.
  `app_upload` fails with a clear error if mtools is missing.
- A compiled 64-bit **VxWorks kernel** (`vxWorks`) for the target BSP.

### Networking: `tap0` (required by the disk/telnet profiles)

The disk profiles launch QEMU with `-net tap,ifname=tap0,script=no,...`. The
`script=no` means **QEMU does not create or configure the tap device** — it must
already exist and be up on the host. The default profiles use the subnet
`192.168.200.0/24` (host `.254`, target `.1`), matching their bootline
(`h=192.168.200.254 e=192.168.200.1`). Create it once per boot session:

```bash
sudo ip tuntap add dev tap0 mode tap
sudo ip addr add 192.168.200.254/24 dev tap0
sudo ip link set tap0 up
```

The target is then reachable at `192.168.200.1` (telnet on port 23).

> **No-setup alternative:** the diskless `vxworks_x86_64_default` profile uses
> QEMU **user-mode networking** (`-net user,hostfwd=...`) which needs **no tap and
> no sudo**. Use it for simple kernel-only boots; use a tap/disk profile when you
> need to upload+run programs or use telnet.

## Disk image: format and how to generate it

Disk-image profiles (`vxworks_x86_64_disk`, …) attach a **raw image containing a
FAT filesystem** (`-drive ...,format=raw`). `app_upload` writes files into the
image's `::/bin/` directory with `mcopy`; VxWorks reads them from `/bin` on the
target. (mtools is used instead of a FUSE mount because fusefat `cp` can corrupt
files mid-write.)

Generate a minimal image the same way the tests do:

```bash
# 1. allocate a raw image
dd if=/dev/zero of=disk.img bs=1M count=64

# 2. put a FAT32 filesystem on it
mkfs.vfat -F 32 disk.img

# 3. create /bin and add your program (or let app_upload do step 3+ at runtime)
mmd  -i disk.img ::/bin
mcopy -i disk.img -D o myapp.vxe ::/bin/myapp.vxe

# verify
mdir -i disk.img ::/bin
```

Pass this image to `start_qemu(..., drive_image="/abs/path/disk.img")`. A full
VxWorks application image (kernel startup script, ROMFS, etc.) is produced by your
board/build system; this server only requires that the result be a raw FAT image
it can `mcopy` into.

## Running the server

```bash
pip install -e ".[dev]"      # fastmcp, pyelftools, pytest
python -m qemu_mcp.main       # stdio MCP transport (for an MCP client)
```

### Claude Desktop config

```json
{
  "mcpServers": {
    "qemu-mcp": {
      "command": "python",
      "args": ["-m", "qemu_mcp.main"]
    }
  }
}
```

(Docker image also available: `docker build -t qemu-mcp-server .`)

## Testing

```bash
# Unit tests — no live QEMU, no kernel needed:
pytest tests/test_vxworks_runtime.py tests/test_image_upload.py -v

#   test_image_upload.py generates a real FAT image (dd + mkfs.vfat), runs the
#   upload() mcopy/mdir round-trip, and verifies the file byte-exact. It SKIPS
#   automatically if mkfs.vfat/mtools are not installed.

# Live integration tests — need a real kernel (and tap0 for disk profiles):
pytest tests/test_vm.py -s -v --kernel-path=/abs/path/to/vxWorks
```

## Project structure

```text
├── pyproject.toml
├── Dockerfile
├── src/qemu_mcp/
│   ├── main.py              # stdio entry point
│   ├── server.py            # FastMCP tool registrations (the agent-facing API)
│   ├── qemu/                # profiles + QEMU process / QMP monitor / serial console
│   │   ├── profile.py       # PROFILES dict (boot args per target)
│   │   ├── vm.py            # subprocess launch, extra_args passthrough
│   │   ├── monitor.py       # QMP over 127.0.0.1:15556
│   │   └── console.py       # serial console over 127.0.0.1:15555
│   └── runtimes/            # OS-specific drivers behind a generic TargetRuntime ABC
│       ├── base.py          # the abstract interface (upload/exec/kill/status/…)
│       ├── loader.py        # os_name → runtime class dispatch
│       └── vxworks/         # VxWorks runtime (RTP exec, EDR capture, mcopy upload)
└── tests/
```

## License

MIT
