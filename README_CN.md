# nacos-mcp-wrapper-python
[English Document](./README.md)  
## 概述
Nacos-mcp-wrapper-python 是一个帮助你快速将 Mcp Server注册到 Nacos 的 SDK。

Nacos 一个更易于构建云原生应用的动态服务发现、配置管理和服务管理平台。Nacos提供了一组简单易用的特性集，帮助您快速实现动态服务发现、服务配置、服务元数据及流量管理。

通过使用Nacos-mcp-wrapper-python 将Mcp Server 注册到Nacos，你可以通过Nacos实现 对 Mcp server Tools及其对应参数的描述进行动态修改，从而助力你的 Mcp Server快速演进。
## 安装

### 环境要求
nacos-mcp-wrapper-python 1.0.0及以上版本，要求Nacos Sever版本 > 3.0.1
- python >=3.10
### 使用 PIP
```bash
pip install nacos-mcp-wrapper-python
```

## 开发
我们可以使用官方社区的 MCP Python SDK 快速构建一个 MCP Server：
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
要快速将你的 Mcp Server 注册到 Nacos，只需将 FastMCP 替换为 NacosMCP：

```python
# server.py
from nacos_mcp_wrapper.server.nacos_mcp import NacosMCP
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings

# Create an MCP server
# mcp = FastMCP("Demo")
nacos_settings = NacosSettings()
nacos_settings.SERVER_ADDR = "<nacos_server_addr> e.g.127.0.0.1:8848"
mcp = NacosMCP("nacos-mcp-python", nacos_settings=nacos_settings,
               port=18001,
               instructions="This is a simple Nacos MCP server",
               version="1.0.0")


# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

mcp.run(transport="sse")
```
在将 Mcp Server 注册到 Nacos 后，你可以在不重启 Mcp Server 的情况下，动态更新 Nacos 上 Mcp Server 中工具及其参数的描述。
### 进阶用法

在使用官方 MCP Python SDK 构建 MCP Server时，如果你需要控制服务器的细节，可以直接使用低级别的Server实现。这将允许你自定义服务器的各个方面，包括通过 lifespan API 进行生命周期管理。
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

要快速将你的 Mcp Server 注册到 Nacos，只需将 Server 替换为 NacosServer：
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

更多示例和使用方式，请参阅 example 目录下的内容。
