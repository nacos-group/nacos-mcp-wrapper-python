import asyncio
import json
import logging
from typing import Literal, Any

import anyio
import mcp.types as types
from mcp.server import FastMCP
from v2.nacos import NacosConfigService, ConfigParam, \
	NacosNamingService, RegisterInstanceParam, ClientConfigBuilder

from nacos_mcp_wrapper.server.nacos_settings import NacosSettings
from nacos_mcp_wrapper.server.mcp_server_info import MCPServerInfo, RemoteServerConfig, \
	ServiceRef
from nacos_mcp_wrapper.server.utils import get_first_non_loopback_ip, ConfigSuffix

logger = logging.getLogger(__name__)

class NacosMCP(FastMCP):

	def __init__(self, nacos_settings: NacosSettings,
			name: str | None = None,
			instructions: str | None = None,
			**settings: Any):
		super().__init__(name, instructions, **settings)
		self._nacos_settings = nacos_settings
		if self._nacos_settings.SERVICE_IP is None:
			self._nacos_settings.SERVICE_IP = get_first_non_loopback_ip()

		naming_client_config_builder = ClientConfigBuilder()
		naming_client_config_builder.server_address(
				self._nacos_settings.SERVER_ADDR).endpoint(
				self._nacos_settings.SERVER_ENDPOINT).namespace_id(
				self._nacos_settings.SERVICE_NAMESPACE).access_key(
				self._nacos_settings.ACCESS_KEY).secret_key(
				self._nacos_settings.SECRET_KEY).app_conn_labels(
				self._nacos_settings.APP_CONN_LABELS)

		if self._nacos_settings.CREDENTIAL_PROVIDER is not None:
			naming_client_config_builder.credentials_provider(
					self._nacos_settings.CREDENTIAL_PROVIDER)

		self._naming_client_config = naming_client_config_builder.build()

		config_client_config_builder = ClientConfigBuilder()
		config_client_config_builder.server_address(
				self._nacos_settings.SERVER_ADDR).endpoint(
				self._nacos_settings.SERVER_ENDPOINT).namespace_id(
				"nacos-default-mcp").access_key(
				self._nacos_settings.ACCESS_KEY).secret_key(
				self._nacos_settings.SECRET_KEY).app_conn_labels(
				self._nacos_settings.APP_CONN_LABELS)

		if self._nacos_settings.CREDENTIAL_PROVIDER is not None:
			naming_client_config_builder.credentials_provider(
					self._nacos_settings.CREDENTIAL_PROVIDER)

		self._config_client_config = config_client_config_builder.build()
		self._tools_meta = {}

	def run(self, transport: Literal["stdio", "sse"] = "stdio") -> None:
		TRANSPORTS = Literal["stdio", "sse"]
		if transport not in TRANSPORTS.__args__:  # type: ignore
			raise ValueError(f"Unknown transport: {transport}")

		if transport == "stdio":
			anyio.run(self.run_stdio_async)
		else:  # transport == "sse"
			anyio.run(self.run_sse_async)

	async def run_stdio_async(self) -> None:
		asyncio.create_task(self.async_nacos_register_mcp(transport="stdio"))
		await super().run_stdio_async()

	async def run_sse_async(self) -> None:
		asyncio.create_task(self.async_nacos_register_mcp(transport="sse"))
		await super().run_sse_async()

	async def tool_list_listener(self, tenant_id: str, group_id: str,
			data_id: str, content: str):
		tool_list = json.loads(content)
		self._tools_meta = tool_list["toolsMeta"]
		for tool in tool_list["tools"]:
			local_tool = self._tool_manager.get_tool(tool["name"])
			if local_tool is None:
				continue
			local_tool.description = tool["description"]

	async def _list_tmp_tools(self) -> list[types.Tool]:
		"""List all available tools."""
		tools = self._tool_manager.list_tools()
		return [
			types.Tool(
					name=info.name,
					description=info.description,
					inputSchema=info.parameters,
			)
			for info in tools if self.is_tool_enabled(info.name)
		]

	def is_tool_enabled(self, tool_name: str) -> bool:
		if tool_name in self._tools_meta:
			if "enabled" in self._tools_meta[tool_name]:
				if not self._tools_meta[tool_name]["enabled"]:
					return False
		return True

	async def async_nacos_register_mcp(self,
			transport: Literal["stdio", "sse"] = "stdio",
	):
		try:
			config_client = await NacosConfigService.create_config_service(
					self._config_client_config)

			mcp_tools_data_id = self._mcp_server.name + ConfigSuffix.TOOLS.value
			mcp_servers_data_id = self._mcp_server.name + ConfigSuffix.MCP_SERVER.value
			if types.ListToolsRequest in self._mcp_server.request_handlers:
				tools = await self._mcp_server.request_handlers[
					types.ListToolsRequest](self)
				tools_dict = tools.model_dump(
						by_alias=True, mode="json", exclude_none=True
				)
				nacos_tools = await config_client.get_config(ConfigParam(
						data_id=mcp_tools_data_id, group="mcp-tools"
				))
				if nacos_tools is not None and nacos_tools != "":
					nacos_tools_dict = json.loads(nacos_tools)
					self._tools_meta = nacos_tools_dict["toolsMeta"]
					for nacos_tool in nacos_tools_dict["tools"]:
						for tool in tools_dict["tools"]:
							if nacos_tool["name"] == tool["name"]:
								tool["description"] = nacos_tool["description"]
								self._tool_manager.get_tool(
										nacos_tool["name"]).description = \
									nacos_tool["description"]
								break
				tools_dict["toolsMeta"] = self._tools_meta
				await config_client.publish_config(ConfigParam(
						data_id=mcp_tools_data_id, group="mcp-tools",
						content=json.dumps(tools_dict, indent=2)
				))
				self._mcp_server.list_tools()(self._list_tmp_tools)
				await config_client.add_listener(mcp_tools_data_id, "mcp-tools",
												 self.tool_list_listener)

			if transport == "stdio":
				mcp_server_info = MCPServerInfo(
						protocol="local",
						name=self._mcp_server.name,
						description=self._mcp_server.instructions,
						version=self._mcp_server.version,
						toolsDescriptionRef=mcp_tools_data_id,
				)

				mcp_server_info_dict = mcp_server_info.model_dump(
						by_alias=True, mode="json", exclude_none=True
				)
				await config_client.publish_config(ConfigParam(
						data_id=mcp_servers_data_id, group="mcp-server",
						content=json.dumps(mcp_server_info_dict, indent=2)
				))
			elif transport == "sse":
				naming_client = await NacosNamingService.create_naming_service(
						self._naming_client_config)

				if self._nacos_settings.SERVICE_REGISTER:
					await naming_client.register_instance(
							request=RegisterInstanceParam(
									group_name=self._nacos_settings.SERVICE_GROUP,
									service_name=self.name + "-mcp-service",
									ip=self._nacos_settings.SERVICE_IP,
									port=self.settings.port,
							)
					)

				mcp_server_info = MCPServerInfo(
						protocol="mcp-sse",
						name=self.name,
						description=self._mcp_server.instructions,
						version=self._mcp_server.version,
						remoteServerConfig=RemoteServerConfig(
								serviceRef=ServiceRef(
										namespaceId=self._nacos_settings.SERVICE_NAMESPACE,
										serviceName=self.name + "-mcp-service",
										groupName=self._nacos_settings.SERVICE_GROUP,
								),
								exportPath="/sse",
						),
						toolsDescriptionRef=mcp_tools_data_id,
				)
				mcp_server_info_dict = mcp_server_info.model_dump(
						by_alias=True, mode="json", exclude_none=True
				)
				await config_client.publish_config(ConfigParam(
						data_id=mcp_servers_data_id, group="mcp-server",
						content=json.dumps(mcp_server_info_dict, indent=2)
				))
		except Exception as e:
			logging.error(f"Failed to register MCP server to Nacos: {e}")

