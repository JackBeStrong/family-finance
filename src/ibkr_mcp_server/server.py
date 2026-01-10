#!/usr/bin/env python3
"""
Interactive Brokers MCP HTTP Server

A Model Context Protocol (MCP) server that exposes Interactive Brokers Flex Query data via HTTP.

Usage:
    IB_FLEX_TOKEN=your_token python -m src.ibkr_mcp_server.server
"""

import json
import logging
import os
import subprocess
import time

from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more visibility
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("mcp").setLevel(logging.WARNING)

# Global instances
_ib_process = None
_request_id_counter = 0


def get_ib_process():
    """Get or create the Interactive Brokers MCP process."""
    global _ib_process
    
    if _ib_process is not None and _ib_process.poll() is None:
        return _ib_process
    
    # Get IB_FLEX_TOKEN from environment
    flex_token = os.getenv("IB_FLEX_TOKEN")
    if not flex_token:
        raise ValueError("IB_FLEX_TOKEN environment variable is required")
    
    logger.info("Starting Interactive Brokers MCP process...")
    
    # Start the npx process
    env = os.environ.copy()
    env["IB_FLEX_TOKEN"] = flex_token
    
    _ib_process = subprocess.Popen(
        ["npx", "-y", "interactive-brokers-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1
    )
    
    logger.info(f"IB MCP process started with PID: {_ib_process.pid}")
    
    # Initialize the MCP connection
    time.sleep(2)  # Give it a moment to start
    _initialize_mcp()
    
    return _ib_process


def _send_jsonrpc(method: str, params: dict = None) -> dict:
    """Send a JSON-RPC request to the IB MCP process."""
    global _request_id_counter
    
    process = get_ib_process()
    
    _request_id_counter += 1
    request_id = _request_id_counter
    
    # Build JSON-RPC request
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {}
    }
    
    # Send request
    request_json = json.dumps(request) + "\n"
    logger.debug(f"→ IB MCP: {request_json.strip()}")
    process.stdin.write(request_json)
    process.stdin.flush()
    
    # Read response
    response_line = process.stdout.readline()
    if not response_line:
        raise RuntimeError("IB MCP process closed stdout")
    
    response = json.loads(response_line)
    logger.debug(f"← IB MCP: {response}")
    
    if "error" in response:
        raise RuntimeError(f"IB MCP error: {response['error']}")
    
    return response.get("result", {})


def _initialize_mcp():
    """Initialize the MCP connection with the IB process."""
    try:
        result = _send_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "ibkr-http-bridge",
                "version": "1.0.0"
            }
        })
        logger.info(f"IB MCP initialized: {result.get('serverInfo', {}).get('name', 'unknown')}")
        
        # Send initialized notification
        _send_jsonrpc("notifications/initialized", {})
        
    except Exception as e:
        logger.error(f"Failed to initialize IB MCP: {e}")
        raise


def _call_ib_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool on the IB MCP server."""
    result = _send_jsonrpc("tools/call", {
        "name": tool_name,
        "arguments": arguments
    })
    return result


# Create the FastMCP server
# Configure host to 0.0.0.0 for external access
mcp = FastMCP("interactive-brokers-mcp", stateless_http=True, host="0.0.0.0", port=8001)


# ==========================================
# INTERACTIVE BROKERS TOOLS
# ==========================================

@mcp.tool()
def get_stock_performance() -> dict:
    """Get Interactive Brokers stock performance data and trading activity.
    
    This retrieves the latest Flex Query report (ID: 1359561) which contains
    comprehensive trading data, positions, and performance metrics.
    """
    # Hardcoded query ID - this is the only query we expose
    arguments = {
        "queryId": "1359561",
        "parseXml": True
    }
    
    try:
        result = _call_ib_tool("get_flex_query", arguments)
        return result
    except Exception as e:
        logger.error(f"Error calling get_flex_query: {e}", exc_info=True)
        return {"error": str(e)}


# Run with streamable HTTP transport
if __name__ == "__main__":
    import atexit
    
    # Register cleanup
    def cleanup():
        global _ib_process
        if _ib_process is not None:
            logger.info("Terminating IB MCP process...")
            _ib_process.terminate()
            try:
                _ib_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("IB MCP process did not terminate, killing...")
                _ib_process.kill()
            _ib_process = None
    
    atexit.register(cleanup)
    
    mcp.run(transport="streamable-http")
