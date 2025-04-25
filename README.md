# nacos-mcp-wrapper-python
Nacos-mcp-wrapper-python helps you quickly register your Mcp Server on Nacos. By using Nacos to host your Mcp Server, it supports dynamic modifications of the descriptions for Mcp Server Tools and their corresponding parameters, assisting in the rapid evolution of your Mcp Server.

## How to use:
python >=3.10
1. Install:
```bash
pip install nacos-mcp-wrapper-python
```
2. Use

Before use nacos-mcp-wrapper-python, 
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
```
Replace the FashMCP with NacosMCP to register your mcp server to nacos

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


You can also replace the Server with NacosServer:
```python
from mcp.server import Server
app = Server("mcp-website-fetcher")
```

change to NacosServer:
```python
from nacos_mcp_wrapper.server.nacos_server import NacosServer
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings

nacos_settings = NacosSettings()
nacos_settings.SERVER_ADDR = "<nacos_server_addr> e.g.127.0.0.1:8848"
app = NacosServer("mcp-website-fetcher",nacos_settings=nacos_settings)
```

For more examples, please refer to the content under the `example` directory.

