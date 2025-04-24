# nacos-mcp-wrapper-python
Nacos mcp wrapper Python sdk

## How to use:
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
nacos_settings.SERVER_ADDR = "<nacos_server_addr>"
mcp = NacosMCP(nacos_settings, "nacos-mcp-python")


# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b
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
nacos_settings.SERVER_ADDR = "<nacos_server_addr>"
app = NacosServer(nacos_settings,"mcp-website-fetcher")
```

For more examples, please refer to the content under the `example` directory.

