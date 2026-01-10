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
# OAUTH 2.0 / OIDC WELL-KNOWN ENDPOINTS
# ==========================================

from starlette.responses import JSONResponse

@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_authorization_server_metadata(request):
    """
    OAuth 2.0 Authorization Server Metadata endpoint (RFC 8414).
    
    This endpoint advertises that the MCP server uses Zitadel for OAuth 2.0 authentication.
    Claude.ai and other OAuth clients will query this endpoint to discover the authorization
    server configuration.
    
    The actual OAuth endpoints are hosted by Zitadel at auth.jackan.xyz.
    """
    # Get the issuer URL from environment or use default (Zitadel)
    issuer = os.getenv("OAUTH_ISSUER", "https://auth.jackan.xyz")
    
    metadata = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/v2/authorize",
        "token_endpoint": f"{issuer}/oauth/v2/token",
        "introspection_endpoint": f"{issuer}/oauth/v2/introspect",
        "userinfo_endpoint": f"{issuer}/oidc/v1/userinfo",
        "revocation_endpoint": f"{issuer}/oauth/v2/revoke",
        "end_session_endpoint": f"{issuer}/oidc/v1/end_session",
        "device_authorization_endpoint": f"{issuer}/oauth/v2/device_authorization",
        "jwks_uri": f"{issuer}/oauth/v2/keys",
        "registration_endpoint": None,
        "scopes_supported": [
            "openid",
            "profile",
            "email",
            "phone",
            "address",
            "offline_access"
        ],
        "response_types_supported": [
            "code",
            "id_token",
            "id_token token"
        ],
        "response_modes_supported": [
            "query",
            "fragment",
            "form_post"
        ],
        "grant_types_supported": [
            "authorization_code",
            "implicit",
            "refresh_token",
            "client_credentials",
            "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "urn:ietf:params:oauth:grant-type:device_code"
        ],
        "subject_types_supported": [
            "public"
        ],
        "id_token_signing_alg_values_supported": [
            "EdDSA",
            "RS256",
            "RS384",
            "RS512",
            "ES256",
            "ES384",
            "ES512"
        ],
        "request_object_signing_alg_values_supported": [
            "RS256"
        ],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_basic",
            "client_secret_post",
            "private_key_jwt"
        ],
        "token_endpoint_auth_signing_alg_values_supported": [
            "RS256"
        ],
        "revocation_endpoint_auth_methods_supported": [
            "none",
            "client_secret_basic",
            "client_secret_post",
            "private_key_jwt"
        ],
        "revocation_endpoint_auth_signing_alg_values_supported": [
            "RS256"
        ],
        "introspection_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "private_key_jwt"
        ],
        "introspection_endpoint_auth_signing_alg_values_supported": [
            "RS256"
        ],
        "claims_supported": [
            "sub",
            "aud",
            "exp",
            "iat",
            "iss",
            "auth_time",
            "nonce",
            "acr",
            "amr",
            "c_hash",
            "at_hash",
            "act",
            "scopes",
            "client_id",
            "azp",
            "preferred_username",
            "name",
            "family_name",
            "given_name",
            "locale",
            "email",
            "email_verified",
            "phone_number",
            "phone_number_verified"
        ],
        "code_challenge_methods_supported": [
            "S256"
        ],
        "ui_locales_supported": [
            "bg",
            "cs",
            "de",
            "en",
            "es",
            "fr",
            "hu",
            "id",
            "it",
            "ja",
            "ko",
            "mk",
            "nl",
            "pl",
            "pt",
            "ro",
            "ru",
            "sv",
            "tr",
            "uk",
            "zh"
        ],
        "request_parameter_supported": True,
        "request_uri_parameter_supported": False
    }
    
    return JSONResponse(content=metadata, headers={
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=3600"
    })


@mcp.custom_route("/.well-known/openid-configuration", methods=["GET"])
async def openid_configuration(request):
    """
    OpenID Connect Discovery endpoint (OIDC Core 1.0).
    
    This is an alias to the OAuth 2.0 authorization server metadata endpoint,
    as both standards define similar discovery mechanisms.
    """
    return await oauth_authorization_server_metadata(request)


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
