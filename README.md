# QEMU MCP Server

An MCP (Model Context Protocol) server that provides Large Language Models with the ability to manage, orchestrate, and interact with hardware-accelerated **QEMU** virtual machines running embedded real-time operating systems (VxWorks/Zephyr).

## Features

- **Automated Profile Discovery**: Embedded ELF header detection via `pyelftools` to match kernels to target hardware configurations.
- **Hardware Acceleration**: High-speed execution using host KVM paths pass-through securely.
- **Headless TCP Console Automation**: Non-blocking serial character interaction over isolated local sockets (`127.0.0.1:15555`).
- **Raw Socket QMP Monitoring**: Direct JSON-RPC control and hardware state extraction over loopback connections (`127.0.0.1:15556`).
- **Dynamic Plugin Loader**: Decoupled, registration-free discovery loop for runtime classes based on target profile names.
- **Ultra-Lean Footprint**: Pure Python process orchestration layout completely independent of heavy external hypervisor testing wrappers.

## Prerequisites

- **Docker** installed and running on a Linux host (with `/dev/kvm` accessible).
- An MCP-compatible client (e.g., [Claude Desktop](https://claude.ai)).
- A compiled 64-bit target kernel image (e.g., VxWorks `itl_generic`).

## Installation & Setup

### 1. Build the Docker Image

The build loop is now highly optimized, lightweight, and compiles instantly from public PyPI wheels.

```bash
docker build -t qemu-mcp-server .
```

### 2. Configure Claude Desktop

Add the execution block to your `~/.config/Claude/claude_desktop_config.json` file.

*Note: We mount your host kernels folder into the container as read-only and explicitly share the hardware virtualization device accelerator layout.*

```json
{
  "mcpServers": {
    "qemu-vxworks-orchestrator": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--device=/dev/kvm",
        "-p", "15555:15555",
        "-p", "15556:15556",
        "-p", "1534:1534",
        "-p", "2345:2345",
        "-v", "$WIND_HOME:/kernels:ro",
        "qemu-mcp-server"
      ]
    }
  }
}
```

## Technical Details

- **Base Layout**: Modern Python `src/` directory packaging conventions.
- **Core Dependencies**:
    - `FastMCP`: High-utility framework for standard static tools generation mapping.
    - `pyelftools`: For raw binary analysis and architecture detection.
    - `psutil`: Local process tree status resource cleaning tracking.

## Development & Testing

### Local Virtual Environment Installation

Initialize dependencies in development mode using your workspace project file definitions:

```bash
# Install package along with testing dependency groups
pip install -e ".[dev]"

# Build your distribution wheel package natively
python3 -m build
```

### Run the Un-Mocked Test Suite

You can execute targeted integration checks directly against a live running hypervisor process inside your shell environment:

```bash
# Terminal 1: Run your precise QEMU command parameters sequence
qemu-system-x86_64 -m 1G -nographic -kernel /path/to/vxWorks -append "bootline:fs(0,0)..." -cpu Nehalem -smp 4 -net nic -net user,hostfwd=tcp::1534-:1534,hostfwd=tcp::2345-:2345 -chardev socket,id=console,host=127.0.0.1,port=15555,server=on,wait=off -serial chardev:console -chardev socket,id=monitor,host=127.0.0.1,port=15556,server=on,wait=off -mon chardev=monitor,mode=control -enable-kvm

# Terminal 2: Run parameter-driven validation loops across our sockets
pytest tests/test_console.py -s -v
pytest tests/test_console_interaction.py -s -v --kernel-path=/path/to/vxWorks
pytest tests/test_vm.py -s -v --kernel-path=/path/to/vxWorks
```

### Project Structure

```text
├── pyproject.toml         # Unified dependency declarations and pytest configurations
├── ARCHITECTURE.md        # Technical data-flow blueprints mapping
├── Dockerfile             # Container orchestration using non-isolated pip compilers
├── src/
│   └── qemu_mcp/
│       ├── main.py        # Python script console entry point execution launcher
│       ├── server.py      # FastMCP tools registrations registry
│       ├── qemu/          # VM instance handling and profile dictionaries configurations
│       └── runtimes/      # Dynamic loader loops and OS table text regex tools parsers
└── tests/                 # 100% Un-mocked, real-kernel interaction integration test cases
```
