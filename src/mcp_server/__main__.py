"""
Entry point for running the MCP server as a module.

Usage:
    python -m src.mcp_server --transport sse --port 8080
    python -m src.mcp_server --transport stdio
"""

from src.mcp_server.server import main

if __name__ == "__main__":
    main()
