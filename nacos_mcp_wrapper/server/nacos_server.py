import json
import logging
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Literal, Callable, AsyncIterator, Any

import jsonref
from mcp import types, Tool
from mcp.server import Server
from mcp.server.lowlevel.server import LifespanResultT
from mcp.server.lowlevel.server import lifespan
from v2.nacos import NacosConfigService, ConfigParam, \
	NacosNamingService, RegisterInstanceParam, ClientConfigBuilder

from nacos_mcp_wrapper.server.mcp_server_info import MCPServerInfo, ServiceRef, \
	RemoteServerConfig
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings
from nacos_mcp_wrapper.server.utils import get_first_non_loopback_ip, \
	ConfigSuffix, jsonref_default

logger = logging.getLogger(__name__)

class NacosServer(Server):
	def __init__(
			self,
			name: str,
			nacos_settings: NacosSettings | None = None,
			version: str | None = None,
			instructions: str | None = None,
			lifespan: Callable[
				[Server[LifespanResultT]], AbstractAsyncContextManager[
					LifespanResultT]
			] = lifespan,
	):
		super().__init__(name, version, instructions, lifespan)

		if nacos_settings == None:
			nacos_settings = NacosSettings()
		if nacos_settings.SERVICE_NAMESPACE == "":
			nacos_settings.SERVICE_NAMESPACE = "public"

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
			config_client_config_builder.credentials_provider(
					self._nacos_settings.CREDENTIAL_PROVIDER)

		self._config_client_config = config_client_config_builder.build()

		self._tmp_tools: dict[str, Tool] = {}
		self._tools_meta = {}
		self._tmp_tools_list_handler = None

	async def _list_tmp_tools(self) -> list[Tool]:
		"""List all available tools."""
		return [
			Tool(
					name=info.name,
					description=info.description,
					inputSchema=info.inputSchema,
			)
			for info in list(self._tmp_tools.values()) if self.is_tool_enabled(
					info.name)
		]

	def is_tool_enabled(self, tool_name: str) -> bool:
		if tool_name in self._tools_meta:
			if "enabled" in self._tools_meta[tool_name]:
				if not self._tools_meta[tool_name]["enabled"]:
					return False
		return True

	async def tool_list_listener(self, tenant_id: str, group_id: str,
			data_id: str, content: str):
		self.update_local_tools(content)

	def update_local_tools(self,nacos_tools:str):
		def update_args_description(_local_args:dict[str, Any], _nacos_args:dict[str, Any]):
			for key, value in _local_args.items():
				if key in _nacos_args and "description" in _nacos_args[key]:
					_local_args[key]["description"] = _nacos_args[key][
						"description"]

		nacos_tools_dict = json.loads(nacos_tools)
		if "toolsMeta" in nacos_tools_dict:
			self._tools_meta = nacos_tools_dict["toolsMeta"]
		if "tools" not in nacos_tools_dict:
			return
		for nacos_tool in nacos_tools_dict["tools"]:
			if nacos_tool["name"] in self._tmp_tools:
				local_tool = self._tmp_tools[nacos_tool["name"]]
				if "description" in nacos_tool:
					local_tool.description = nacos_tool["description"]

				local_args = local_tool.inputSchema["properties"]
				nacos_args = nacos_tool["inputSchema"]["properties"]
				update_args_description(local_args, nacos_args)
				break

	async def init_tools_tmp(self):
		_tmp_tools = await self.request_handlers[
			types.ListToolsRequest](
				self)
		for _tmp_tool in _tmp_tools.root.tools:
			self._tmp_tools[_tmp_tool.name] = _tmp_tool
		self._tmp_tools_list_handler = self.request_handlers[
			types.ListToolsRequest]

		for tool in self._tmp_tools.values():
			resolved_data = jsonref.JsonRef.replace_refs(tool.inputSchema)
			resolved_data = json.dumps(resolved_data, default=jsonref_default)
			resolved_data = json.loads(resolved_data)
			tool.inputSchema = resolved_data

	async def register_to_nacos(self,
			transport: Literal["stdio", "sse"] = "stdio",
			port: int = 8000,
			path: str = "/sse"):
		try:
			config_client = await NacosConfigService.create_config_service(
					self._config_client_config)

			mcp_tools_data_id = self.name + ConfigSuffix.TOOLS.value
			mcp_servers_data_id = self.name + ConfigSuffix.MCP_SERVER.value

			if types.ListToolsRequest in self.request_handlers:
				await self.init_tools_tmp()
				self.list_tools()(self._list_tmp_tools)

				nacos_tools = await config_client.get_config(ConfigParam(
						data_id=mcp_tools_data_id, group="mcp-tools"
				))
				if nacos_tools is not None and nacos_tools != "":
					self.update_local_tools(nacos_tools)
				_tmp_tools = await self.request_handlers[
					types.ListToolsRequest](
						self)
				tools_dict = _tmp_tools.model_dump(
						by_alias=True, mode="json", exclude_none=True
				)
				tools_dict["toolsMeta"] = self._tools_meta
				await config_client.publish_config(ConfigParam(
						data_id=mcp_tools_data_id, group="mcp-tools",
						content=json.dumps(tools_dict, indent=2)
				))
				self.list_tools()(self._list_tmp_tools)
				await config_client.add_listener(mcp_tools_data_id, "mcp-tools",
												 self.tool_list_listener)

			server_info_content = await config_client.get_config(ConfigParam(
						data_id=mcp_servers_data_id, group="mcp-server"
			))

			server_description = self.name
			if self.instructions is not None:
				server_description = self.instructions
			if server_info_content is not None and server_info_content != "":
				server_info_dict = json.loads(server_info_content)
				if "description" in server_info_dict:
					server_description = server_info_dict["description"]

			if transport == "stdio":
				mcp_server_info = MCPServerInfo(
						protocol="local",
						name=self.name,
						description=server_description,
						version=self.version,
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
				if self._nacos_settings.SERVICE_REGISTER:
					naming_client = await NacosNamingService.create_naming_service(
							self._naming_client_config)

					await naming_client.register_instance(
							request=RegisterInstanceParam(
									group_name=self._nacos_settings.SERVICE_GROUP,
									service_name=self.name + "-mcp-service",
									ip=self._nacos_settings.SERVICE_IP,
									port=port,
									ephemeral=self._nacos_settings.SERVICE_EPHEMERAL,
							)
					)
				mcp_server_info = MCPServerInfo(
						protocol="mcp-sse",
						name=self.name,
						description=self.instructions,
						version=self.version,
						remoteServerConfig=RemoteServerConfig(
								serviceRef=ServiceRef(
										namespaceId=self._nacos_settings.SERVICE_NAMESPACE,
										serviceName=self.name + "-mcp-service",
										groupName=self._nacos_settings.SERVICE_GROUP
								),
								exportPath=path,
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
