#!/usr/bin/env python3
"""
Token API MCP Server - Auto-generated from REST OpenAPI
"""

import asyncio
import logging
import os
import sys

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from utils import patch_openapi_spec_for_keywords

# Configuration
API_BASE_URL = os.getenv("TOKEN_API_BASE_URL", "http://localhost:8000")
OPENAPI_SPEC_URL = os.getenv("OPENAPI_SPEC_URL", f"{API_BASE_URL}/openapi")
VERSION_URL = f"{API_BASE_URL}/v1/version"
API_TOKEN = os.getenv("API_TOKEN", "")
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8080"))
MCP_TRANSPORT = "streamable-http"
VERSION_CHECK_INTERVAL = int(os.getenv("VERSION_CHECK_INTERVAL", "300"))  # 5 minutes

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
CURRENT_VERSION = None
OPENAPI_SPEC = None
MCP_INSTANCE = None
HTTP_CLIENT = None


def fetch_openapi_spec():
    """Fetch OpenAPI spec from Token API"""
    logger.info(f"Fetching OpenAPI spec from {OPENAPI_SPEC_URL}")
    try:
        response = httpx.get(OPENAPI_SPEC_URL, timeout=10.0)
        response.raise_for_status()
        spec = response.json()

        # Validate that we got an OpenAPI spec
        if "openapi" not in spec or "paths" not in spec:
            logger.error(f"Invalid OpenAPI spec received. Response: {spec}")
            return None

        logger.info(f"Successfully loaded OpenAPI spec with {len(spec.get('paths', {}))} endpoints")

        # Patch the spec in memory to handle Python keywords before passing it to FastMCP.
        # This is to avoid deserialization errors with Pydantic from API responses.
        logger.info("Patching OpenAPI spec to handle conflicting keywords...")
        patched_spec = patch_openapi_spec_for_keywords(spec)

        return patched_spec
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching OpenAPI spec: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Network error fetching OpenAPI spec: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching OpenAPI spec: {e}")
        return None


def fetch_api_version():
    """Fetch current API version"""
    try:
        response = httpx.get(VERSION_URL, timeout=5.0)
        response.raise_for_status()
        version_info = response.json()
        return version_info.get("version") or version_info.get("commit") or version_info.get("date")
    except Exception as e:
        logger.warning(f"Failed to fetch API version: {e}")
        return None


def create_mcp_from_openapi(spec):
    """Create MCP server from OpenAPI specification"""
    try:
        # Create HTTP client with authentication
        client = httpx.AsyncClient(
            base_url=API_BASE_URL, headers={"Authorization": f"Bearer: {API_TOKEN}"} if API_TOKEN else {}, timeout=30.0
        )

        # Generate MCP server from OpenAPI spec
        mcp = FastMCP.from_openapi(client=client, openapi_spec=spec, name="Token API MCP", version="1.0.0")

        @mcp.custom_route("/health", methods=["GET"])
        async def health_check(request: Request) -> PlainTextResponse:
            return PlainTextResponse("OK")

        return mcp, client
    except Exception as e:
        logger.error(f"Failed to create MCP server from OpenAPI spec: {e}")
        return None, None


async def reload_mcp_server():
    """Reload the MCP server with updated OpenAPI spec"""
    global OPENAPI_SPEC, MCP_INSTANCE, HTTP_CLIENT, CURRENT_VERSION

    logger.info("Reloading MCP server with updated OpenAPI spec...")

    # Fetch new spec
    new_spec = fetch_openapi_spec()
    if not new_spec:
        logger.error("Failed to fetch new OpenAPI spec, keeping current instance")
        return False

    # Create new MCP instance
    new_mcp, new_client = create_mcp_from_openapi(new_spec)
    if not new_mcp:
        logger.error("Failed to create new MCP instance, keeping current instance")
        return False

    # Close old client
    if HTTP_CLIENT:
        try:
            await HTTP_CLIENT.aclose()
        except Exception as e:
            logger.warning(f"Error closing old HTTP client: {e}")

    # Update globals
    OPENAPI_SPEC = new_spec
    MCP_INSTANCE = new_mcp
    HTTP_CLIENT = new_client
    CURRENT_VERSION = fetch_api_version()

    logger.info(f"✅ MCP server reloaded successfully! New version: {CURRENT_VERSION}")
    logger.info(f"   Loaded {len(OPENAPI_SPEC.get('paths', {}))} endpoints")

    return True


async def check_version_and_reload():
    """Background task to check for API version changes and reload"""
    global CURRENT_VERSION

    while True:
        await asyncio.sleep(VERSION_CHECK_INTERVAL)

        try:
            new_version = fetch_api_version()

            if new_version and new_version != CURRENT_VERSION:
                logger.info(f"🔄 Token API version changed: {CURRENT_VERSION} → {new_version}")

                success = await reload_mcp_server()

                if success:
                    logger.info("MCP server hot-reloaded successfully")
                else:
                    logger.error("Failed to reload MCP server, continuing with old version")
            else:
                logger.debug(f"Version check: API version unchanged ({CURRENT_VERSION})")

        except Exception as e:
            logger.error(f"Error during version check: {e}")


async def main():
    global OPENAPI_SPEC, MCP_INSTANCE, HTTP_CLIENT, CURRENT_VERSION

    # Initial fetch
    logger.info("Initializing Token API MCP Server...")
    OPENAPI_SPEC = fetch_openapi_spec()
    if not OPENAPI_SPEC:
        logger.error(f"Failed to load OpenAPI spec. Make sure the Token API is running at {API_BASE_URL}")
        sys.exit(1)

    CURRENT_VERSION = fetch_api_version()
    logger.info(f"Token API version: {CURRENT_VERSION}")

    # Create initial MCP instance
    MCP_INSTANCE, HTTP_CLIENT = create_mcp_from_openapi(OPENAPI_SPEC)
    if not MCP_INSTANCE:
        logger.error("Failed to create initial MCP instance")
        sys.exit(1)

    logger.info(f"Starting Token API MCP server on {MCP_HOST}:{MCP_PORT}")
    logger.info(f"Version check interval: {VERSION_CHECK_INTERVAL} seconds")
    logger.info("Hot-reload enabled: Server will auto-update when API changes")

    # Start background version checker
    version_check_task = asyncio.create_task(check_version_and_reload())

    try:
        await MCP_INSTANCE.run_async(transport=MCP_TRANSPORT, host=MCP_HOST, port=MCP_PORT)
    finally:
        version_check_task.cancel()
        if HTTP_CLIENT:
            await HTTP_CLIENT.aclose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
