from nacos_mcp_wrapper.server.nacos_mcp import NacosMCP
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings

# Create an MCP server instance
nacos_settings = NacosSettings()
nacos_settings.SERVER_ADDR = "127.0.0.1:8848" # <nacos_server_addr> e.g. 127.0.0.1:8848
nacos_settings.USERNAME=""
nacos_settings.PASSWORD=""
mcp = NacosMCP("nacos-mcp-python", nacos_settings=nacos_settings,
               port=18001,
               instructions="This is a simple Nacos MCP server",
               version="1.0.0")

# Register an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers together"""
    return a + b

# Register a subtraction tool
@mcp.tool()
def minus(a: int, b: int) -> int:
    """Subtract two numbers"""
    return a - b

# Register a prompt function
@mcp.prompt()
def get_prompt(topic: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {topic}!"

# Register a dynamic resource endpoint
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"

if __name__ == "__main__":
    try:
        mcp.run(transport="sse")
    except Exception as e:
        print(f"Runtime error: {e}")