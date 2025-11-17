#!/usr/bin/env python3
"""
Test suite for Token API MCP Server
Tests tool invocations and response validation using FastMCP Client
"""

import json
import logging

import os
import httpx
import pytest
import pytest_asyncio
from fastmcp.client import Client
from fastmcp.client.transports import FastMCPTransport

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mark all tests as asyncio
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def mcp_instance():
    from src.server import TOKEN_API_BASE_URL, create_mcp_from_openapi, fetch_openapi_spec

    """Fixture to create MCP instance for testing"""
    logger.info("Creating MCP instance for testing...")

    auth_token = os.getenv("TOKEN_API_AUTH_TOKEN", None)
    if not auth_token:
        pytest.skip("Missing authorization token")

    # Fetch OpenAPI spec
    spec = fetch_openapi_spec()
    if not spec:
        pytest.skip("Failed to load OpenAPI spec.")

    client = httpx.AsyncClient(
        base_url=TOKEN_API_BASE_URL,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=30.0,
    )

    if not client:
        pytest.skip("Failed to create HTTPX client")

    # Create MCP instance
    mcp = create_mcp_from_openapi(spec, client)
    if not mcp:
        pytest.skip("Failed to create MCP instance")

    logger.info(f"✅ MCP instance created with {len(spec.get('paths', {}))} endpoints")

    yield mcp

    # Cleanup
    logger.info("Closing HTTP client...")
    await client.aclose()


@pytest_asyncio.fixture
async def mcp_client(mcp_instance):
    """Fixture to create MCP client for each test"""
    async with Client(transport=mcp_instance) as client:
        yield client


async def test_server_initialization(mcp_client: Client[FastMCPTransport]):
    """Test that the MCP server initializes correctly"""
    logger.info("\n=== Testing Server Initialization ===")

    # List available tools
    tools = await mcp_client.list_tools()
    logger.info(f"Available tools: {len(tools)}")

    assert len(tools) > 0, "No tools available on server"
    logger.info("✅ Server initialization test passed")


async def test_health_endpoint(mcp_client: Client[FastMCPTransport]):
    """Test the health check endpoint"""
    logger.info("\n=== Testing Health Endpoint ===")

    result = await mcp_client.call_tool(name="getV1Health", arguments={"skip_endpoints": True})

    logger.debug(f"Health check result: {result}")

    # Validate response structure
    assert result.content is not None, "No content in response"
    content = result.content[0]
    assert content.type == "text", f"Expected text content, got {content.type}"

    data = json.loads(content.text)
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "checks" in data
    assert "database" in data["checks"]

    logger.info("✅ Health endpoint test passed")


async def test_version_endpoint(mcp_client: Client[FastMCPTransport]):
    """Test the version endpoint"""
    logger.info("\n=== Testing Version Endpoint ===")

    result = await mcp_client.call_tool(name="getV1Version", arguments={})

    logger.debug(f"Version result: {result}")

    content = result.content[0]
    data = json.loads(content.text)

    assert "version" in data
    assert "commit" in data
    assert "date" in data

    logger.info(f"✅ Version endpoint test passed - Version: {data['version']}")


async def test_networks_endpoint(mcp_client: Client[FastMCPTransport]):
    """Test the networks endpoint"""
    logger.info("\n=== Testing Networks Endpoint ===")

    result = await mcp_client.call_tool(name="getV1Networks", arguments={})

    logger.debug(f"Networks result: {result}")

    content = result.content[0]
    data = json.loads(content.text)

    assert "networks" in data
    assert len(data["networks"]) > 0

    # Validate network structure
    network = data["networks"][0]
    assert "id" in network
    assert "fullName" in network
    assert "networkType" in network

    logger.info(f"✅ Networks endpoint test passed - Found {len(data['networks'])} networks")


async def test_evm_balances(mcp_client: Client[FastMCPTransport]):
    """Test EVM token balances endpoint"""
    logger.info("\n=== Testing EVM Balances ===")

    # Test address: Vitalik's address
    test_address = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"

    result = await mcp_client.call_tool(
        name="getV1EvmBalances", arguments={"network": "mainnet", "address": test_address, "limit": 5}
    )

    logger.debug(f"EVM Balances result: {result}")

    content = result.content[0]
    data = json.loads(content.text)

    assert "data" in data
    assert "pagination" in data
    assert "statistics" in data

    if len(data["data"]) > 0:
        balance = data["data"][0]
        assert "address" in balance
        assert "contract" in balance
        assert "amount" in balance
        assert "symbol" in balance

    logger.info(f"✅ EVM Balances test passed - Found {len(data['data'])} balances")


async def test_evm_native_balance(mcp_client: Client[FastMCPTransport]):
    """Test EVM native balance endpoint"""
    logger.info("\n=== Testing EVM Native Balance ===")

    test_address = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"

    result = await mcp_client.call_tool(
        name="getV1EvmBalancesNative", arguments={"network": "mainnet", "address": test_address}
    )

    logger.debug(f"Native Balance result: {result}")

    content = result.content[0]
    data = json.loads(content.text)

    assert "data" in data
    if len(data["data"]) > 0:
        balance = data["data"][0]
        assert "value" in balance
        assert "symbol" in balance
        assert balance["symbol"] == "ETH"

    logger.info("✅ EVM Native Balance test passed")


async def test_evm_tokens(mcp_client: Client[FastMCPTransport]):
    """Test EVM token metadata endpoint"""
    logger.info("\n=== Testing EVM Token Metadata ===")

    # USDC contract
    usdc_contract = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"

    result = await mcp_client.call_tool(
        name="getV1EvmTokens", arguments={"network": "mainnet", "contract": usdc_contract}
    )

    logger.debug(f"Token Metadata result: {result}")

    content = result.content[0]
    data = json.loads(content.text)

    assert "data" in data
    if len(data["data"]) > 0:
        token = data["data"][0]
        assert "name" in token
        assert "symbol" in token
        assert "decimals" in token
        assert token["symbol"] == "USDC"

    logger.info("✅ EVM Token Metadata test passed")


async def test_evm_transfers(mcp_client: Client[FastMCPTransport]):
    """Test EVM transfers endpoint"""
    logger.info("\n=== Testing EVM Transfers ===")

    test_address = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"

    result = await mcp_client.call_tool(
        name="getV1EvmTransfers",
        arguments={"network": "mainnet", "from_address": test_address, "limit": 3, "start_time": "2025-10-01"},
    )

    logger.debug(f"Transfers result: {result}")

    content = result.content[0]
    data = json.loads(content.text)

    assert "data" in data
    if len(data["data"]) > 0:
        transfer = data["data"][0]
        assert "transaction_id" in transfer
        assert "from" in transfer
        assert "to" in transfer
        assert "amount" in transfer

    logger.info(f"✅ EVM Transfers test passed - Found {len(data['data'])} transfers")


async def test_svm_balances(mcp_client: Client[FastMCPTransport]):
    """Test Solana token balances endpoint"""
    logger.info("\n=== Testing SVM Balances ===")

    # Example Solana address
    test_owner = "GXYBNgyYKbSLr938VJCpmGLCUaAHWsncTi7jDoQSdFR9"

    result = await mcp_client.call_tool(
        name="getV1SvmBalances", arguments={"network": "solana", "owner": test_owner, "limit": 5}
    )

    logger.debug(f"SVM Balances result: {result}")

    content = result.content[0]
    data = json.loads(content.text)

    assert "data" in data
    if len(data["data"]) > 0:
        balance = data["data"][0]
        assert "owner" in balance
        assert "mint" in balance
        assert "amount" in balance

    logger.info(f"✅ SVM Balances test passed - Found {len(data['data'])} balances")


async def test_evm_dexes(mcp_client: Client[FastMCPTransport]):
    """Test EVM DEXes endpoint"""
    logger.info("\n=== Testing EVM DEXes ===")

    result = await mcp_client.call_tool(name="getV1EvmDexes", arguments={"network": "mainnet", "limit": 5})

    logger.debug(f"EVM DEXes result: {result}")

    content = result.content[0]
    data = json.loads(content.text)

    assert "data" in data
    if len(data["data"]) > 0:
        dex = data["data"][0]
        assert "factory" in dex
        assert "protocol" in dex
        assert "transactions" in dex

    logger.info(f"✅ EVM DEXes test passed - Found {len(data['data'])} DEXes")


async def test_error_handling(mcp_client: Client[FastMCPTransport]):
    """Test error handling with invalid parameters"""
    logger.info("\n=== Testing Error Handling ===")

    # Try with invalid network - should raise an error
    with pytest.raises(Exception) as exc_info:
        await mcp_client.call_tool(
            name="getV1EvmBalances", arguments={"network": "invalid_network", "address": "0x123"}
        )

    logger.info(f"✅ Error handling test passed - Got expected error: {str(exc_info.value)[:100]}")
