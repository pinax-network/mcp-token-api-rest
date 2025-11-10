import os

from fastmcp import FastMCP

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp")

# Create a proxy to a remote server
proxy = FastMCP.as_proxy(MCP_SERVER_URL, name="Remote Server Proxy")

if __name__ == "__main__":
    proxy.run()  # Runs via STDIO for Claude Desktop
