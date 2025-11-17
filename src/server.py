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
from fastmcp.server.middleware import Middleware, MiddlewareContext
from key_value.aio.stores.memory import MemoryStore
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from src.utils import patch_openapi_spec_for_keywords

# Configuration
TOKEN_API_BASE_URL = os.getenv("TOKEN_API_BASE_URL", "http://localhost:8000")
OPENAPI_SPEC_URL = os.getenv("OPENAPI_SPEC_URL", f"{TOKEN_API_BASE_URL}/openapi")
VERSION_URL = f"{TOKEN_API_BASE_URL}/v1/version"
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8080"))
MCP_TRANSPORT = "streamable-http"
VERSION_CHECK_INTERVAL = int(os.getenv("VERSION_CHECK_INTERVAL", "600"))
ACTIVE_SESSION_TTL = int(os.getenv("ACTIVE_SESSION_TTL", "600"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(message)s (%(filename)s:%(lineno)s)",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Global state
CURRENT_VERSION = None
OPENAPI_SPEC = None
MCP_INSTANCE = None
HTTP_CLIENT = None
ACTIVE_SESSIONS = MemoryStore()  # Track active client sessions to notify for OpenAPI updates


class SessionTrackingMiddleware(Middleware):
    async def on_request(self, context: MiddlewareContext, call_next):
        if context.fastmcp_context:
            try:
                session_id = context.fastmcp_context.session_id
                session = context.fastmcp_context.session

                value = await ACTIVE_SESSIONS.get(session_id)
                if value and not value.get("notified"):
                    await session.send_tool_list_changed()
                    logger.info("✅ Sent an update notification to an active client")

                await ACTIVE_SESSIONS.put(session_id, {"notified": 1}, ttl=ACTIVE_SESSION_TTL)
                logger.info(f"Tracking session (total: {len(await ACTIVE_SESSIONS.keys())})")
            except Exception as e:
                logger.error(f"Exception while tracking session: {e}")
                pass

        result = await call_next(context)
        return result


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


def fetch_api_version() -> str | None:
    """Fetch current API version"""
    try:
        response = httpx.get(VERSION_URL, timeout=5.0)
        response.raise_for_status()
        version_info = response.json()
        return version_info.get("version")
    except Exception as e:
        logger.warning(f"Failed to fetch API version: {e}")
        return None


def create_mcp_from_openapi(spec, client):
    """Create MCP server from OpenAPI specification using existing HTTP client"""
    try:
        mcp = FastMCP.from_openapi(client=client, openapi_spec=spec, name="Token API MCP", version="1.0.0")

        @mcp.custom_route("/health", methods=["GET"])
        async def _(_: Request) -> PlainTextResponse:
            return PlainTextResponse("OK")

        # Add session tracking middleware
        mcp.add_middleware(SessionTrackingMiddleware())

        return mcp
    except Exception as e:
        logger.error(f"Failed to create MCP server from OpenAPI spec: {e}")
        return None


async def reload_mcp_server(new_version: str):
    """Reload the MCP server with updated OpenAPI spec"""
    global OPENAPI_SPEC, MCP_INSTANCE, CURRENT_VERSION
    logger.info("Reloading MCP server with updated OpenAPI spec...")

    # Fetch new spec
    new_spec = fetch_openapi_spec()
    if not new_spec:
        logger.error("Failed to fetch new OpenAPI spec, keeping current instance")
        return False

    if MCP_INSTANCE:
        # Create new MCP instance using the existing HTTP client
        new_mcp = create_mcp_from_openapi(new_spec, HTTP_CLIENT)
        if not new_mcp:
            logger.error("Failed to create new MCP instance, keeping current instance")
            return False

        # Mark all active sessions to be notified of changes
        sessions = await ACTIVE_SESSIONS.keys()
        await ACTIVE_SESSIONS.put_many(sessions, [{"notified": 0}] * len(sessions))

        # Update globals
        MCP_INSTANCE = new_mcp
        OPENAPI_SPEC = new_spec
        CURRENT_VERSION = new_version

        logger.info(f"✅ MCP server reloaded successfully! New version: {CURRENT_VERSION}")
        logger.info(f"Loaded {len(OPENAPI_SPEC.get('paths', {}))} endpoints")

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

                success = await reload_mcp_server(new_version)

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
        logger.error(f"Failed to load OpenAPI spec. Make sure the Token API is running at {TOKEN_API_BASE_URL}")
        sys.exit(1)

    CURRENT_VERSION = fetch_api_version()
    logger.info(f"Token API version: {CURRENT_VERSION}")

    # Create persistent HTTP client
    HTTP_CLIENT = httpx.AsyncClient(
        base_url=TOKEN_API_BASE_URL,
        timeout=30.0,
    )
    logger.info("Created persistent HTTP client")

    # Create initial MCP instance
    MCP_INSTANCE = create_mcp_from_openapi(OPENAPI_SPEC, HTTP_CLIENT)
    if not MCP_INSTANCE:
        logger.error("Failed to create initial MCP instance")
        await HTTP_CLIENT.aclose()
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
            logger.info("HTTP client closed")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
