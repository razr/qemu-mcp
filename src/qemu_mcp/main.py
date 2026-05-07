import sys
from .server import mcp

def main():
    """
    Entry point for the QEMU MCP Server.
    Run this via your MCP client using: python -m qemu_mcp.main
    """
    try:
        # transport="stdio" is the standard for MCP clients like Claude Desktop
        mcp.run(transport="stdio")
    except Exception as e:
        # Errors must go to stderr; stdout is reserved for JSON-RPC messages
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

