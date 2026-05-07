# QEMU MCP Server

An MCP (Model Context Protocol) server that provides Large Language Models with the ability to manage, orchestrate, and interact with **QEMU** virtual machines.

## Features

- **Lifecycle Management**: Start, stop, and monitor QEMU processes using the `qemu.machine` library.
- **QMP Integration**: Low-level communication with VMs via the QEMU Machine Protocol (`qemu.qmp`).
- **Multi-Arch Support**: Pre-installed binaries for `x86_64` and `ARM` architectures.
- **Dockerized Environment**: Encapsulates all complex system dependencies, ensuring the Python management tools match the installed QEMU binary versions.

## Prerequisites

- **Docker** installed and running.
- An MCP-compatible client (e.g., [Claude Desktop](https://claude.ai)).

## Installation & Setup

### 1. Build the Docker Image
The build process automatically synchronizes the `qemu.machine` Python tooling from the official QEMU source to match the system's binary version.

```bash
docker build -t qemu-mcp-server .
```

### 2. Configure Claude Desktop
Add the server to your `claude_desktop_config.json`. 

*Note: We use `-i` (interactive) to allow the MCP protocol to communicate over `stdio` inside the container.*

```json
{
  "mcpServers": {
    "qemu-manager": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "qemu-mcp-server"
      ]
    }
  }
}
```

## Technical Details

- **Base Image**: `python:3.12-slim` (Debian Bookworm).
- **Core Dependencies**: 
    - `FastMCP`: Framework for MCP server implementation.
    - `qemu.machine`: Internal QEMU library for process control.
    - `qemu.qmp`: Official library for QEMU Machine Protocol communication.
    - `psutil` & `pyelftools`: For system monitoring and binary analysis.

## Development

If you add new Python dependencies, update the `RUN pip install` section in the `Dockerfile`. To test the server locally through Docker:

```bash
docker run -it --rm qemu-mcp-server
```

### Project Structure

- `Dockerfile`: Orchestrates the installation of QEMU binaries and sparse-checkouts the Python in-tree modules.
- `setup.py`: Defines the `qemu-mcp` entry point for the CLI.
- `qemu_mcp/`: Contains the MCP tools and resource definitions.

