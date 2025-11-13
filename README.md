# Token API MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes The Graph's Token API through Claude and other AI assistants. This server automatically generates tools from the Token API's OpenAPI specification and supports hot-reloading when the API is updated.

The Token API provides blockchain data for EVM networks (Ethereum, Arbitrum, Base, etc.), Solana, and TRON, including token balances, transfers, NFT data, and DEX swaps.

The MCP client is required to interact with the MCP server:
https://github.com/pinax-network/pinax-mcp

Other useful links:
- URL: https://token-api.thegraph.com/
- Getting started: https://thegraph.com/docs/en/token-api/quick-start/
- Repo: https://github.com/pinax-network/token-api

## Installation

Install using uv (recommended):

```bash
uv pip install git+https://github.com/pinax-network/mcp-token-api-rest.git
```

Or with pip:

```bash
pip install git+https://github.com/pinax-network/mcp-token-api-rest.git
```

For development, clone the repository and install in editable mode:

```bash
git clone https://github.com/pinax-network/mcp-token-api-rest.git
cd mcp-token-api-rest
uv pip install -e .
```

## Usage

Start the MCP server:

```bash
python -m src.server
```

The server will connect to the Token API at `http://localhost:8000` by default and expose its endpoints as MCP tools. You can customize the connection using environment variables:

```bash
export TOKEN_API_BASE_URL=https://token-api.thegraph.com
export TOKEN_API_AUTH_TOKEN=your-jwt-token
export VERSION_CHECK_INTERVAL=300
python -m src.server
```

Once running, the server listens on `http://localhost:8080` and provides tools for querying blockchain data. For example, through Claude you could ask "What's Vitalik's ETH balance on mainnet?" and it would use the appropriate Token API endpoints.

The server checks for API updates every 5 minutes (configurable) and hot-reloads the OpenAPI specification without requiring a restart.

## Docker

Build and run with Docker:

```bash
docker build -t mcp-token-api .
docker run -p 8080:8080 -e TOKEN_API_BASE_URL=http://your-token-api:8000 mcp-token-api
```

## Configuration

Configuration is done through environment variables:

`TOKEN_API_BASE_URL` sets the Token API endpoint (default: http://localhost:8000)

`TOKEN_API_AUTH_TOKEN` provides authentication if required

`MCP_HOST` and `MCP_PORT` control where the MCP server listens (default: 0.0.0.0:8080)

`VERSION_CHECK_INTERVAL` sets how often to check for API updates in seconds (default: 300)

## Testing

Run the test suite:

```bash
pytest tests/test_server.py -v
```

Skip integration tests that require a running Token API:

```bash
pytest tests/test_server.py -v -m "not integration"
```

## License

[Apache-2.0](LICENSE)
