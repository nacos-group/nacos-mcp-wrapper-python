# nacos-mcp-wrapper-python

[中文文档](./README_CN.md)  

## Overview
Nacos-mcp-wrapper-python is a sdk that helps you quickly register your Mcp Server to Nacos. Nacos is an easy-to-use platform designed for dynamic service discovery and configuration and service management. It helps you to build cloud native applications and microservices platform easily. By using Nacos to host your Mcp Server, it supports dynamic modifications of the descriptions for Mcp Server Tools and their corresponding parameters, assisting in the rapid evolution of your Mcp Server.

## Installation

### Environment
Starting from version 1.0.0 of nacos-mcp-wrapper-python, the Nacos server version must be greater than 3.0.1.
- python >=3.10
### Use pip
```bash
pip install nacos-mcp-wrapper-python
```

## Development
We can use official MCP Python SDK to quickly build a mcp server:
```python
# server.py
from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Demo")


# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

mcp.run(transport="sse")
```
To quickly register your Mcp Server to Nacos, just replace the FashMCP with NacosMCP:

```python
# server.py
from nacos_mcp_wrapper.server.nacos_mcp import NacosMCP
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings

# Create an MCP server
# mcp = FastMCP("Demo")
nacos_settings = NacosSettings()
nacos_settings.SERVER_ADDR = "<nacos_server_addr> e.g.127.0.0.1:8848"
mcp = NacosMCP("nacos-mcp-python",nacos_settings=nacos_settings)


# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

mcp.run(transport="sse")
```
After registering to Nacos, you can dynamically update the descriptions of Tools and the descriptions of parameters in the Mcp Server on Nacos without restarting your Mcp Server.

### Advanced Usage

When building an MCP server using the official MCP Python SDK, for more control, you can directly use the low-level server implementation, for more control, you can use the low-level server implementation directly. This gives you full access to the protocol and allows you to customize every aspect of your server, including lifecycle management through the lifespan API.
```python
import mcp.server.stdio
import mcp.types as types
import httpx
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

# Create a server instance
server = Server("example-server")


async def fetch_website(
    url: str,
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    headers = {
        "User-Agent": "MCP Test Server (github.com/modelcontextprotocol/python-sdk)"
    }
    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
        return [types.TextContent(type="text", text=response.text)]
    
@server.call_tool()
async def fetch_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name != "fetch":
        raise ValueError(f"Unknown tool: {name}")
    if "url" not in arguments:
        raise ValueError("Missing required argument 'url'")
    return await fetch_website(arguments["url"])

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="fetch",
            description="Fetches a website and returns its content",
            inputSchema={
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    }
                },
            },
        )
    ]


async def run():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="example",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
```

To quickly register your Mcp Server to Nacos, just replace the Server with NacosServer:

```python
import mcp.server.stdio
import mcp.types as types
import httpx
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions
from nacos_mcp_wrapper.server.nacos_server import NacosServer
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings

# Create a server instance
# server = Server("example-server")
nacos_settings = NacosSettings()
nacos_settings.SERVER_ADDR = "<nacos_server_addr> e.g.127.0.0.1:8848"
server = NacosServer("mcp-website-fetcher",nacos_settings=nacos_settings)

async def fetch_website(
    url: str,
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    headers = {
        "User-Agent": "MCP Test Server (github.com/modelcontextprotocol/python-sdk)"
    }
    async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
        return [types.TextContent(type="text", text=response.text)]
    
@server.call_tool()
async def fetch_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name != "fetch":
        raise ValueError(f"Unknown tool: {name}")
    if "url" not in arguments:
        raise ValueError("Missing required argument 'url'")
    return await fetch_website(arguments["url"])

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="fetch",
            description="Fetches a website and returns its content",
            inputSchema={
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    }
                },
            },
        )
    ]


async def run():
    await server.register_to_nacos("stdio")
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="example",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())

```

For more examples, please refer to the content under the `example` directory.

