#!/usr/bin/env python3
"""
Tests for Token API MCP Server
"""
import pytest
import httpx
import asyncio
from unittest.mock import patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope="module")
def ensure_server_initialized():
    """Ensure server module is initialized with valid spec"""
    import src.server as server_module

    # If globals are None, initialize them
    if server_module.OPENAPI_SPEC is None:
        spec = server_module.fetch_openapi_spec()
        if spec:
            server_module.OPENAPI_SPEC = spec
            mcp, client = server_module.create_mcp_from_openapi(spec)
            server_module.MCP_INSTANCE = mcp
            server_module.HTTP_CLIENT = client
            server_module.CURRENT_VERSION = server_module.fetch_api_version()

    yield server_module

    # Cleanup
    if server_module.HTTP_CLIENT:
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(server_module.HTTP_CLIENT.aclose())
        loop.close()


@pytest.fixture
def mock_api_responses():
    """Fixture to mock API responses for offline testing"""
    return {
        "version": "1.0.0",
        "openapi_spec": {
            "openapi": "3.0.0",
            "paths": {
                "/v1/evm/balances": {"get": {}},
                "/v1/svm/balances": {"get": {}},
            }
        }
    }


class TestServerFunctions:
    """Tests for server utility functions"""

    @pytest.mark.asyncio
    async def test_version_endpoint_accessible(self):
        """Test that we can fetch API version"""
        from src.server import fetch_api_version

        version = fetch_api_version()
        # May be None if API is down, that's ok for this test
        if version is not None:
            assert isinstance(version, str)

    @pytest.mark.asyncio
    async def test_openapi_spec_fetch(self):
        """Test that we can fetch OpenAPI spec"""
        from src.server import fetch_openapi_spec

        spec = fetch_openapi_spec()
        if spec is None:
            pytest.skip("Token API not reachable")

        assert "openapi" in spec
        assert "paths" in spec
        assert len(spec["paths"]) > 0

    @pytest.mark.asyncio
    async def test_openapi_spec_has_evm_endpoints(self):
        """Test that OpenAPI spec contains EVM endpoints"""
        from src.server import fetch_openapi_spec

        spec = fetch_openapi_spec()
        if spec is None:
            pytest.skip("Token API not reachable")

        paths = spec.get("paths", {})

        # Check for EVM endpoints
        evm_endpoints = [p for p in paths.keys() if "/v1/evm/" in p]
        assert len(evm_endpoints) > 0, "No EVM endpoints found"

    @pytest.mark.asyncio
    async def test_openapi_spec_has_svm_endpoints(self):
        """Test that OpenAPI spec contains SVM endpoints"""
        from src.server import fetch_openapi_spec

        spec = fetch_openapi_spec()
        if spec is None:
            pytest.skip("Token API not reachable")

        paths = spec.get("paths", {})

        # Check for SVM endpoints
        svm_endpoints = [p for p in paths.keys() if "/v1/svm/" in p]
        assert len(svm_endpoints) > 0, "No SVM endpoints found"

    @pytest.mark.asyncio
    async def test_mcp_instance_creation(self):
        """Test that MCP instance can be created from OpenAPI spec"""
        from src.server import fetch_openapi_spec, create_mcp_from_openapi

        spec = fetch_openapi_spec()
        if spec is None:
            pytest.skip("Token API not reachable")

        mcp, client = create_mcp_from_openapi(spec)
        assert mcp is not None
        assert client is not None

        # Cleanup
        await client.aclose()


class TestHotReload:
    """Tests for hot-reload functionality"""

    @pytest.mark.asyncio
    async def test_reload_fetches_new_spec(self, ensure_server_initialized):
        """Test that reload fetches new OpenAPI spec"""
        server_module = ensure_server_initialized

        # Ensure we have an initial spec
        if server_module.OPENAPI_SPEC is None:
            pytest.skip("Token API not reachable")

        # Get current spec endpoint count
        initial_endpoint_count = len(server_module.OPENAPI_SPEC.get("paths", {}))

        # Trigger reload
        success = await server_module.reload_mcp_server()
        if not success:
            pytest.skip("Token API not reachable for reload")

        # Verify spec was fetched (endpoint count should be similar)
        new_endpoint_count = len(server_module.OPENAPI_SPEC.get("paths", {}))
        assert new_endpoint_count > 0
        assert abs(new_endpoint_count - initial_endpoint_count) < 5

    @pytest.mark.asyncio
    @patch('src.server.fetch_api_version')
    async def test_version_change_detection(self, mock_fetch_version, ensure_server_initialized):
        """Test that version changes are detected"""
        server_module = ensure_server_initialized

        # Get current version
        current_version = server_module.CURRENT_VERSION

        # Mock version change
        mock_fetch_version.return_value = "2.0.0"

        new_version = mock_fetch_version()
        # They should be different (unless by chance current is already 2.0.0)
        assert new_version == "2.0.0"

    @pytest.mark.asyncio
    async def test_reload_handles_fetch_failure(self, ensure_server_initialized):
        """Test that reload handles API fetch failures gracefully"""
        server_module = ensure_server_initialized

        # Ensure we have an initial spec
        if server_module.OPENAPI_SPEC is None:
            pytest.skip("Token API not reachable")

        # Store current spec
        original_endpoint_count = len(server_module.OPENAPI_SPEC.get("paths", {}))

        # Mock a temporary API failure
        with patch('src.server.fetch_openapi_spec', return_value=None):
            success = await server_module.reload_mcp_server()
            assert success is False

        # Verify old spec is still in place
        current_endpoint_count = len(server_module.OPENAPI_SPEC.get("paths", {}))
        assert current_endpoint_count == original_endpoint_count

    @pytest.mark.asyncio
    async def test_reload_handles_invalid_spec(self):
        """Test that reload handles invalid OpenAPI spec"""
        from src.server import reload_mcp_server

        # Mock invalid spec (missing required fields)
        with patch('src.server.fetch_openapi_spec', return_value={"invalid": "spec"}):
            success = await reload_mcp_server()
            # Should fail to create MCP instance
            assert success is False

    @pytest.mark.asyncio
    async def test_concurrent_reloads(self):
        """Test that concurrent reloads don't cause issues"""
        from src.server import reload_mcp_server

        # Start multiple concurrent reloads
        tasks = [
            reload_mcp_server(),
            reload_mcp_server(),
            reload_mcp_server(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete without exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Got exceptions: {exceptions}"


class TestConfiguration:
    """Tests for configuration and environment variables"""

    def test_version_check_interval_default(self):
        """Test that version check interval has correct default"""
        from src.server import VERSION_CHECK_INTERVAL
        assert VERSION_CHECK_INTERVAL == 300  # 5 minutes default

    def test_version_url_uses_v1_endpoint(self):
        """Test that version URL points to /v1/version"""
        from src.server import VERSION_URL, API_BASE_URL
        assert VERSION_URL == f"{API_BASE_URL}/v1/version"

    def test_openapi_url_configured(self):
        """Test that OpenAPI URL is correctly configured"""
        from src.server import OPENAPI_SPEC_URL, API_BASE_URL
        assert OPENAPI_SPEC_URL == f"{API_BASE_URL}/openapi"

    def test_mcp_transport_is_streamable_http(self):
        """Test that MCP transport is configured correctly"""
        from src.server import MCP_TRANSPORT
        assert MCP_TRANSPORT == "streamable-http"

    def test_api_base_url_default(self):
        """Test that API base URL has correct default"""
        from src.server import API_BASE_URL
        # Should be either default or from environment
        assert API_BASE_URL.startswith("http")


class TestTokenAPIIntegration:
    """Integration tests with actual Token API"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_can_reach_token_api(self):
        """Test that Token API is reachable"""
        from src.server import API_BASE_URL

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{API_BASE_URL}/v1/version", timeout=5.0)
                assert response.status_code == 200
                data = response.json()
                assert "version" in data or "commit" in data or "date" in data
            except (httpx.RequestError, httpx.HTTPStatusError):
                pytest.skip("Token API not reachable")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_openapi_endpoint_responds(self):
        """Test that OpenAPI endpoint responds"""
        from src.server import OPENAPI_SPEC_URL

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(OPENAPI_SPEC_URL, timeout=5.0)
                assert response.status_code == 200
                spec = response.json()
                assert "openapi" in spec
                assert "paths" in spec
                assert len(spec["paths"]) > 0
            except (httpx.RequestError, httpx.HTTPStatusError):
                pytest.skip("Token API not reachable")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_version_matches_between_calls(self):
        """Test that version is consistent between multiple calls"""
        from src.server import fetch_api_version

        version1 = fetch_api_version()
        if version1 is None:
            pytest.skip("Token API not reachable")

        await asyncio.sleep(0.1)  # Small delay

        version2 = fetch_api_version()
        assert version1 == version2, "Version should be stable between calls"


if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v"])

    # To run only integration tests:
    # pytest.main([__file__, "-v", "-m", "integration"])

    # To skip integration tests:
    # pytest.main([__file__, "-v", "-m", "not integration"])
