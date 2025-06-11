import asyncio
import json
import logging
from contextlib import AbstractAsyncContextManager
from typing import Literal, Callable, Any

import jsonref
from maintainer.ai.model.nacos_mcp_info import McpToolMeta, McpServerDetailInfo, \
	McpTool, McpServiceRef, McpToolSpecification, McpServerBasicInfo, \
	McpEndpointSpec, McpServerRemoteServiceConfig
from maintainer.ai.model.registry_mcp_info import ServerVersionDetail
from maintainer.ai.nacos_mcp_service import NacosAIMaintainerService
from maintainer.common.ai_maintainer_client_config_builder import \
	AIMaintainerClientConfigBuilder
from mcp import types, Tool
from mcp.server import Server
from mcp.server.lowlevel.server import LifespanResultT, RequestT
from mcp.server.lowlevel.server import lifespan

from v2.nacos import NacosNamingService, RegisterInstanceParam, \
	ClientConfigBuilder, NacosException

from nacos_mcp_wrapper.server.nacos_settings import NacosSettings
from nacos_mcp_wrapper.server.utils import get_first_non_loopback_ip, \
	jsonref_default, compare

logger = logging.getLogger(__name__)

TRANSPORT_MAP = {
    "stdio": "stdio",
    "sse": "mcp-sse",
    "streamable-http": "mcp-streamable",
}

class NacosServer(Server):
	def __init__(
			self,
			name: str,
			nacos_settings: NacosSettings | None = None,
			version: str | None = None,
			instructions: str | None = None,
			lifespan: Callable[
				[Server[LifespanResultT, RequestT]],
				AbstractAsyncContextManager[LifespanResultT],
			] = lifespan,
	):
		if version is None:
			version = "1.0.0"
		super().__init__(name, version, instructions, lifespan)

		if nacos_settings == None:
			nacos_settings = NacosSettings()
		if nacos_settings.NAMESPACE == "":
			nacos_settings.NAMESPACE = "public"

		self._nacos_settings = nacos_settings
		if self._nacos_settings.SERVICE_IP is None:
			self._nacos_settings.SERVICE_IP = get_first_non_loopback_ip()



		ai_client_config_builder = AIMaintainerClientConfigBuilder()
		ai_client_config_builder.server_address(
				self._nacos_settings.SERVER_ADDR).access_key(
				self._nacos_settings.ACCESS_KEY).secret_key(
				self._nacos_settings.SECRET_KEY).username(
				self._nacos_settings.USERNAME).password(
				self._nacos_settings.PASSWORD).app_conn_labels(
				self._nacos_settings.APP_CONN_LABELS)

		if self._nacos_settings.CREDENTIAL_PROVIDER is not None:
			ai_client_config_builder.credentials_provider(
					self._nacos_settings.CREDENTIAL_PROVIDER)

		self._ai_client_config = ai_client_config_builder.build()

		naming_client_config_builder = ClientConfigBuilder()
		naming_client_config_builder.server_address(
				self._nacos_settings.SERVER_ADDR).namespace_id(
				self._nacos_settings.NAMESPACE).access_key(
				self._nacos_settings.ACCESS_KEY).secret_key(
				self._nacos_settings.SECRET_KEY).username(
				self._nacos_settings.USERNAME).password(
				self._nacos_settings.PASSWORD).app_conn_labels(
				self._nacos_settings.APP_CONN_LABELS)

		if self._nacos_settings.CREDENTIAL_PROVIDER is not None:
			naming_client_config_builder.credentials_provider(
					self._nacos_settings.CREDENTIAL_PROVIDER)

		self._naming_client_config = naming_client_config_builder.build()

		self._tmp_tools: dict[str, Tool] = {}
		self._tools_meta: dict[str, McpToolMeta] = {}
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
		if self._tools_meta is None:
			return True
		if tool_name in self._tools_meta:
			mcp_tool_meta = self._tools_meta[tool_name]
			if mcp_tool_meta.enabled is not None:
				if not mcp_tool_meta.enabled:
					return False
		return True

	def update_tools(self,server_detail_info:McpServerDetailInfo):

		def update_args_description(_local_args:dict[str, Any], _nacos_args:dict[str, Any]):
			for key, value in _local_args.items():
				if key in _nacos_args and "description" in _nacos_args[key]:
					_local_args[key]["description"] = _nacos_args[key][
						"description"]

		tool_spec = server_detail_info.toolSpec
		if tool_spec is None:
			return
		if tool_spec.toolsMeta is None:
			self._tools_meta = {}
		else:
			self._tools_meta = tool_spec.toolsMeta
		if tool_spec.tools is None:
			return
		for tool in tool_spec.tools:
			if tool.name in self._tmp_tools:
				local_tool = self._tmp_tools[tool.name]
				if tool.description is not None:
					local_tool.description = tool.description

				local_args = local_tool.inputSchema["properties"]
				nacos_args = tool.inputSchema["properties"]
				update_args_description(local_args, nacos_args)
				continue


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

	def check_tools_compatible(self,server_detail_info:McpServerDetailInfo) -> bool:
		if (server_detail_info.toolSpec is None
				or server_detail_info.toolSpec.tools is None or len(server_detail_info.toolSpec.tools) == 0):
			return True
		tools_spec = server_detail_info.toolSpec
		tools_in_nacos = {}
		for tool in tools_spec.tools:
			tools_in_nacos[tool.name] = tool

		tools_in_local = {}
		for name,tool in self._tmp_tools.items():
			tools_in_local[name] = McpTool(
					name=tool.name,
					description=tool.description,
					inputSchema=tool.inputSchema,
			)
		if tools_in_nacos.keys() != tools_in_local.keys():
			return False

		for name,tool in tools_in_nacos.items():
			str_tools_in_nacos = tool.model_dump_json(exclude_none=True)
			str_tools_in_local = tools_in_local[name].model_dump_json(exclude_none=True)
			if not compare(str_tools_in_nacos, str_tools_in_local):
				return False

		return True


	def check_compatible(self,server_detail_info:McpServerDetailInfo) -> bool:
		if server_detail_info.version != self.version:
			return False
		if server_detail_info.protocol != self.type:
			return False
		if types.ListToolsRequest in self.request_handlers:
			checkToolsResult = self.check_tools_compatible(server_detail_info)
			if not checkToolsResult:
				return False
		mcp_service_ref = server_detail_info.remoteServerConfig.serviceRef
		if not self.is_service_ref_same(mcp_service_ref):
			return False

		return True

	def is_service_ref_same(self,mcp_service_ref:McpServiceRef) -> bool:
		if self.get_register_service_name() != mcp_service_ref.serviceName:
			return False
		if mcp_service_ref.groupName != self._nacos_settings.SERVICE_GROUP:
			return False
		if mcp_service_ref.namespaceId != self._nacos_settings.NAMESPACE:
			return False
		return True


	def get_register_service_name(self) -> str:
		if self._nacos_settings.SERVICE_NAME is not None:
			return self._nacos_settings.SERVICE_NAME
		else:
			return self.name + "::" + self.version

	async def subscribe(self):
		while True:
			try:
				await asyncio.sleep(30)
			except asyncio.TimeoutError:
				logging.debug("Timeout occurred")
			except asyncio.CancelledError:
				return

			try:
				server_detail_info = await self.mcp_service.get_mcp_server_detail(
						self._nacos_settings.NAMESPACE,
						self.name,
						self.version
				)
				print(server_detail_info.model_dump_json())
				if server_detail_info is not None:
					self.update_tools(server_detail_info)
			except Exception as e:
				logging.info(
					f"can not found McpServer info from nacos,{self.name},version:{self.version}")

	async def register_to_nacos(self,
			transport: Literal["stdio", "sse","streamable-http"] = "stdio",
			port: int = 8000,
			path: str = "/sse"):
		try:
			self.type = TRANSPORT_MAP.get(transport, None)
			self.mcp_service = await NacosAIMaintainerService.create_mcp_service(
					self._ai_client_config
			)
			server_detail_info = None
			try:
				server_detail_info = await self.mcp_service.get_mcp_server_detail(
						self._nacos_settings.NAMESPACE,
						self.name,
						self.version
				)
			except Exception as e:
				logging.info(f"can not found McpServer info from nacos,{self.name},version:{self.version}")

			if types.ListToolsRequest in self.request_handlers:
				await self.init_tools_tmp()
				self.list_tools()(self._list_tmp_tools)

			if server_detail_info is not None:
				if not self.check_compatible(server_detail_info):
					logging.error(f"mcp server info is not compatible,{self.name},version:{self.version}")
					raise NacosException(
							f"mcp server info is not compatible,{self.name},version:{self.version}"
					)
				if types.ListToolsRequest in self.request_handlers:
					self.update_tools(server_detail_info)
				asyncio.create_task(self.subscribe())
				return

			mcp_tool_specification = None
			if types.ListToolsRequest in self.request_handlers:
				tool_spec = [
					McpTool(
							name=tool.name,
							description=tool.description,
							inputSchema=tool.inputSchema,
					)
					for tool in list(self._tmp_tools.values())
				]
				mcp_tool_specification = McpToolSpecification(
						tools=tool_spec
				)

			server_version_detail = ServerVersionDetail()
			server_version_detail.version = self.version
			server_basic_info = McpServerBasicInfo()
			server_basic_info.name = self.name
			server_basic_info.versionDetail = server_version_detail
			server_basic_info.description = self.instructions or self.name

			endpoint_spec = McpEndpointSpec()
			if self.type == "stdio":
				server_basic_info.protocol = self.type
				server_basic_info.frontProtocol = self.type
			else:
				endpoint_spec.type = "REF"
				data = {
					"serviceName": self.get_register_service_name(),
					"groupName": self._nacos_settings.SERVICE_GROUP,
					"namespaceId": self._nacos_settings.NAMESPACE,
				}
				endpoint_spec.data = data

				remote_server_config_info = McpServerRemoteServiceConfig()
				remote_server_config_info.exportPath = path
				server_basic_info.remoteServerConfig = remote_server_config_info
				server_basic_info.protocol = self.type
				server_basic_info.frontProtocol = self.type
				if self._nacos_settings.SERVICE_REGISTER:
					naming_client = await NacosNamingService.create_naming_service(
							self._naming_client_config)
					await naming_client.register_instance(
							request=RegisterInstanceParam(
									group_name=self._nacos_settings.SERVICE_GROUP,
									service_name=self.get_register_service_name(),
									ip=self._nacos_settings.SERVICE_IP,
									port=self._nacos_settings.SERVICE_PORT if self._nacos_settings.SERVICE_PORT else port,
									ephemeral=self._nacos_settings.SERVICE_EPHEMERAL,
							)
					)

			await self.mcp_service.create_mcp_server(self._nacos_settings.NAMESPACE,
											   self.name,
											   server_basic_info,
											   mcp_tool_specification,
											   endpoint_spec)
		except Exception as e:
			logging.error(f"Failed to register MCP server to Nacos: {e}")
