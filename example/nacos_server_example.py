import asyncio
import anyio
import click
import httpx
import mcp.types as types
from mcp.server import Server

from nacos_mcp_wrapper.server.nacos_server import NacosServer
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings


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


@click.command()
@click.option("--port", default=18002, help="Port to listen on for SSE")
@click.option("--server_addr", default="127.0.0.1:8848", help="Nacos server address")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="sse",
    help="Transport type",
)
def main(port: int, transport: str, server_addr: str) -> int:
    nacos_settings = NacosSettings()
    nacos_settings.SERVER_ADDR = server_addr
    # app = Server("mcp-website-fetcher")
    app = NacosServer("mcp-website-fetcher",nacos_settings=nacos_settings)

    @app.call_tool()
    async def fetch_tool(
        name: str, arguments: dict
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if name != "fetch":
            raise ValueError(f"Unknown tool: {name}")
        if "url" not in arguments:
            raise ValueError("Missing required argument 'url'")
        return await fetch_website(arguments["url"])

    @app.list_tools()
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

    if transport == "sse":
        async def run_sse_sync():
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Mount, Route

            sse = SseServerTransport("/messages/")

            async def handle_sse(request):
                async with sse.connect_sse(
                    request.scope, request.receive, request._send
                ) as streams:
                    # 0 input stream, 1 output stream
                    await app.run(
                        streams[0], streams[1], app.create_initialization_options()
                    )

            starlette_app = Starlette(
                debug=True,
                routes=[
                    Route("/sse", endpoint=handle_sse),
                    Mount("/messages/", app=sse.handle_post_message),
                ],
            )

            import uvicorn

            await app.register_to_nacos("sse", port,"/sse")

            config = uvicorn.Config(
                    starlette_app,
                    host="0.0.0.0",
                    port=port,
            )
            server = uvicorn.Server(config)
            await server.serve()

        asyncio.run(run_sse_sync())
    elif transport == "stdio":
        from mcp.server.stdio import stdio_server

        async def run_stdio_sync():
            await app.register_to_nacos(transport="stdio")
            async with stdio_server() as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        anyio.run(run_stdio_sync)

    return 0


if __name__ == "__main__":
    main()