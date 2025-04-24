from nacos_mcp_wrapper.server.nacos_mcp import NacosMCP
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings

# Create an MCP server
# mcp = FastMCP("Demo")
nacos_settings = NacosSettings()
nacos_settings.SERVER_ADDR = "<nacos_server_addr>"
mcp = NacosMCP(nacos_settings, "nacos-mcp-python")
# Add an addition tool

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
def minus(a: int, b: int) -> int:
    """Subtract two numbers"""
    return a - b

@mcp.prompt()
def get_prompt(topic: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {topic}!"

@mcp.resource("greeting://{name}")
def get_resource(name: str) -> str:
    """Get a file"""
    return f"Hello, {name}!"

# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"

if __name__ == "__main__":
    try:
        mcp.run(transport="sse")
    except ValueError as e:
        print(f"运行时发生错误: {e}")
