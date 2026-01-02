"""
Entry point for running the MCP server as a module.

Usage:
    python -m src.mcp_server                    # Default: Streamable HTTP on port 8000
    python -m src.mcp_server --port 8001        # Custom port
    python -m src.mcp_server --transport stdio  # Stdio transport
"""

from src.mcp_server.server import main

if __name__ == "__main__":
    main()
