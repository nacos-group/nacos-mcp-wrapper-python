import click
from nacos_mcp_wrapper.server.nacos_mcp import NacosMCP
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings
from datetime import datetime


@click.command()
@click.option("--port", default=18003, help="Port to listen on for SSE")
@click.option("--name", default="nacos-simple-mcp", help="The name of the MCP service")
@click.option("--server_addr", default="127.0.0.1:8848", help="Nacos server address")
def main(port: int, name: str, server_addr: str):
    # Registration settings for Nacos
    nacos_settings = NacosSettings()
    nacos_settings.SERVER_ADDR = server_addr
    nacos_settings.USERNAME = ""
    nacos_settings.PASSWORD = ""
    mcp = NacosMCP(name=name, nacos_settings=nacos_settings, port=port)

    @mcp.tool()
    def get_datetime() -> str:
        """Get current datetime as string"""
        return datetime.now().isoformat()  # 返回字符串格式的时间

    try:
        mcp.run(transport="sse")
    except ValueError as e:
        print(f"Runtime errors: {e}")

if __name__ == "__main__":
    main()