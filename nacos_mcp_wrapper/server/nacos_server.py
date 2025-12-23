import asyncio
import json
import logging
from contextlib import AbstractAsyncContextManager
from typing import Literal, Callable, Any
from importlib import metadata

import jsonref
from mcp import types, Tool
from mcp.server import Server
from mcp.server.lowlevel.server import LifespanResultT, RequestT
from mcp.server.lowlevel.server import lifespan

from v2.nacos import RegisterInstanceParam, \
	ClientConfigBuilder, NacosException, NacosNamingService
from v2.nacos.ai.model.ai_param import GetMcpServerParam, \
	RegisterMcpServerEndpointParam, ReleaseMcpServerParam, \
	SubscribeMcpServerParam
from v2.nacos.ai.model.mcp.mcp import McpToolMeta, McpServerDetailInfo, McpTool, \
	McpServiceRef, McpToolSpecification, McpServerBasicInfo, \
	McpServerRemoteServiceConfig, McpEndpointSpec
from v2.nacos.ai.model.mcp.registry import ServerVersionDetail
from v2.nacos.ai.nacos_ai_service import NacosAIService

from nacos_mcp_wrapper.server.nacos_settings import NacosSettings
from nacos_mcp_wrapper.server.utils import get_first_non_loopback_ip, \
	jsonref_default, compare, pkg_version

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
			website_url: str | None = None,
			icons: list[types.Icon] | None = None,
			lifespan: Callable[
				[Server[LifespanResultT, RequestT]],
				AbstractAsyncContextManager[LifespanResultT],
			] = lifespan,
	):
		if version is None:
			version = pkg_version("mcp")
		super().__init__(name=name,
						 version=version,
						 instructions=instructions,
						 website_url=website_url,
						 icons=icons,
						 lifespan=lifespan)

		if nacos_settings == None:
			nacos_settings = NacosSettings()
		if nacos_settings.NAMESPACE == "":
			nacos_settings.NAMESPACE = "public"

		self._nacos_settings = nacos_settings
		if self._nacos_settings.SERVICE_IP is None:
			self._nacos_settings.SERVICE_IP = get_first_non_loopback_ip()

		self._type: str | None = None
		ai_client_config_builder = ClientConfigBuilder()
		ai_client_config_builder.server_address(
				self._nacos_settings.SERVER_ADDR).namespace_id(
				self._nacos_settings.NAMESPACE).access_key(
				self._nacos_settings.ACCESS_KEY).secret_key(
				self._nacos_settings.SECRET_KEY).username(
				self._nacos_settings.USERNAME).password(
				self._nacos_settings.PASSWORD).app_conn_labels(
				self._nacos_settings.APP_CONN_LABELS)

		if self._nacos_settings.CREDENTIAL_PROVIDER is not None:
			ai_client_config_builder.credentials_provider(
					self._nacos_settings.CREDENTIAL_PROVIDER)

		self._ai_client_config = ai_client_config_builder.build()

		self._nacos_ai_service: NacosAIService | None = None

		self._nacos_naming_service: NacosNamingService | None = None

		self._tmp_tools: dict[str, Tool] = {}
		self._tools_meta: dict[str, McpToolMeta] = {}
		self._tmp_tools_list_handler = None

	async def _list_tmp_tools(self) -> list[Tool]:
		"""List all available tools."""
		return [
			info for info in list(self._tmp_tools.values()) if
			self.is_tool_enabled(
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

	def update_tools(self, server_detail_info: McpServerDetailInfo):

		def update_args_description(_local_args: dict[str, Any],
				_nacos_args: dict[str, Any]):
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
				None)
		for _tmp_tool in _tmp_tools.root.tools:
			self._tmp_tools[_tmp_tool.name] = _tmp_tool
		self._tmp_tools_list_handler = self.request_handlers[
			types.ListToolsRequest]

		for tool in self._tmp_tools.values():
			resolved_data = jsonref.JsonRef.replace_refs(tool.inputSchema)
			resolved_data = json.dumps(resolved_data, default=jsonref_default)
			resolved_data = json.loads(resolved_data)
			tool.inputSchema = resolved_data

	def check_tools_compatible(self,
			server_detail_info: McpServerDetailInfo) -> bool:
		if (server_detail_info.toolSpec is None
				or server_detail_info.toolSpec.tools is None or len(
						server_detail_info.toolSpec.tools) == 0):
			return True
		tools_spec = server_detail_info.toolSpec
		tools_in_nacos = {}
		for tool in tools_spec.tools:
			tools_in_nacos[tool.name] = tool

		tools_in_local = {}
		for name, tool in self._tmp_tools.items():
			tools_in_local[name] = McpTool(
					name=tool.name,
					description=tool.description,
					inputSchema=tool.inputSchema,
			)
		if tools_in_nacos.keys() != tools_in_local.keys():
			return False

		for name, tool in tools_in_nacos.items():
			str_tools_in_nacos = tool.model_dump_json(exclude_none=True)
			str_tools_in_local = tools_in_local[name].model_dump_json(
					exclude_none=True)
			if not compare(str_tools_in_nacos, str_tools_in_local):
				return False

		return True

	def check_compatible(self, server_detail_info: McpServerDetailInfo) -> (
			bool, str):
		if server_detail_info.version != self.version:
			return False, f"version not compatible, local version:{self.version}, remote version:{server_detail_info.version}"
		if server_detail_info.protocol != self._type:
			return False, f"protocol not compatible, local protocol:{self._type}, remote protocol:{server_detail_info.protocol}"
		if types.ListToolsRequest in self.request_handlers:
			check_tools_result = self.check_tools_compatible(server_detail_info)
			if not check_tools_result:
				return False, f"tools not compatible, local tools:{self._tmp_tools}, remote tools:{server_detail_info.toolSpec}"
		mcp_service_ref = server_detail_info.remoteServerConfig.serviceRef
		is_same_service, error_msg = self.is_service_ref_same(mcp_service_ref)
		if not is_same_service:
			return False, error_msg

		return True, ""

	def is_service_ref_same(self, mcp_service_ref: McpServiceRef) -> (
			bool, str):
		if self._nacos_settings.SERVICE_NAME is not None and self._nacos_settings.SERVICE_NAME != mcp_service_ref.serviceName:
			return False, f"service name not compatible, local service name:{self._nacos_settings.SERVICE_NAME}, remote service name:{mcp_service_ref.serviceName}"
		if self._nacos_settings.SERVICE_GROUP is not None and self._nacos_settings.SERVICE_GROUP != mcp_service_ref.groupName:
			return False, f"group name not compatible, local group name:{self._nacos_settings.SERVICE_GROUP}, remote group name:{mcp_service_ref.groupName}"
		if mcp_service_ref.namespaceId != self._nacos_settings.NAMESPACE:
			return False, f"namespace id not compatible, local namespace id:{self._nacos_settings.NAMESPACE}, remote namespace id:{mcp_service_ref.namespaceId}"
		return True, ""

	def get_register_service_name(self) -> str:
		if self._nacos_settings.SERVICE_NAME is not None:
			return self._nacos_settings.SERVICE_NAME
		else:
			return self.name + "::" + self.version

	async def _subscribe_call_back(self, mcp_id: str, namespace_id: str,
			mcp_name: str, mcp_server_detail_info: McpServerDetailInfo):
		logger.info(
				f"mcp_id:{mcp_id}, namespace_id:{namespace_id},"
				f" mcp_name:{mcp_name} changed, mcp_server_detail_info:{McpServerDetailInfo}")
		self.update_tools(mcp_server_detail_info)

	async def subscribe(self):
		await self._nacos_ai_service.subscribe_mcp_server(
				SubscribeMcpServerParam(
						mcp_name=self.name,
						version=self.version,
						subscribe_callback=self._subscribe_call_back
				))

	async def register_to_nacos(self,
			transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
			port: int = 8000,
			path: str = "/sse"):
		try:
			self._type = TRANSPORT_MAP.get(transport, None)
			self._nacos_ai_service = await NacosAIService.create_ai_service(
					self._ai_client_config
			)
			self._nacos_naming_service = await NacosNamingService.create_naming_service(
					self._ai_client_config
			)
			server_detail_info = None
			try:
				server_detail_info = await self._nacos_ai_service.get_mcp_server(
						GetMcpServerParam(
								mcp_name=self.name,
								version=self.version
						))
			except Exception as e:
				logger.info(
						f"can not found McpServer info from nacos,{self.name},version:{self.version}")

			if types.ListToolsRequest in self.request_handlers:
				await self.init_tools_tmp()
				self.list_tools()(self._list_tmp_tools)

			if server_detail_info is not None:
				is_compatible, error_msg = self.check_compatible(
						server_detail_info)
				if not is_compatible:
					logger.error(
							f"mcp server info is not compatible,{self.name},version:{self.version},reason:{error_msg}")
					raise NacosException(
							f"mcp server info is not compatible,{self.name},version:{self.version},reason:{error_msg}"
					)
				if types.ListToolsRequest in self.request_handlers:
					self.update_tools(server_detail_info)
				if self._nacos_settings.SERVICE_REGISTER and (
						self._type == "mcp-sse"
						or self._type == "mcp-streamable"):
					version = metadata.version('nacos-mcp-wrapper-python')
					service_meta_data = {
						"source": f"nacos-mcp-wrapper-python-{version}",
						**self._nacos_settings.SERVICE_META_DATA}
					await self._nacos_naming_service.register_instance(
							request=RegisterInstanceParam(
									group_name=server_detail_info.remoteServerConfig.serviceRef.groupName,
									service_name=server_detail_info.remoteServerConfig.serviceRef.serviceName,
									ip=self._nacos_settings.SERVICE_IP,
									port=self._nacos_settings.SERVICE_PORT if self._nacos_settings.SERVICE_PORT else port,
									ephemeral=self._nacos_settings.SERVICE_EPHEMERAL,
									metadata=service_meta_data
							)
					)
				await self.subscribe()
				logger.info(
						f"Register to nacos success,{self.name},version:{self.version}")
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
			if self._type == "stdio":
				server_basic_info.protocol = self._type
				server_basic_info.frontProtocol = self._type
			else:
				endpoint_spec.type = "REF"
				data = {
					"serviceName": self.get_register_service_name(),
					"groupName": "DEFAULT_GROUP" if self._nacos_settings.SERVICE_GROUP is None else self._nacos_settings.SERVICE_GROUP,
					"namespaceId": self._nacos_settings.NAMESPACE,
				}
				endpoint_spec.data = data

				remote_server_config_info = McpServerRemoteServiceConfig()
				remote_server_config_info.exportPath = path
				server_basic_info.remoteServerConfig = remote_server_config_info
				server_basic_info.protocol = self._type
				server_basic_info.frontProtocol = self._type
			_server = None
			try:
				_server = await self._nacos_ai_service.get_mcp_server(
						GetMcpServerParam(
								mcp_name=self.name,
								version=self.version
						))
			except NacosException as e:
				pass
			try:
				if _server is None:
					await self._nacos_ai_service.release_mcp_server(
							ReleaseMcpServerParam(
									server_spec=server_basic_info,
									tool_spec=mcp_tool_specification,
									mcp_endpoint_spec=endpoint_spec
							))
				else:
					_is_compatible, error_msg = self.check_compatible(
							_server)
					if not _is_compatible:
						logger.error(
								f"mcp server info is not compatible,{self.name},version:{self.version},reason:{error_msg}")
						raise NacosException(
								f"mcp server info is not compatible,{self.name},version:{self.version},reason:{error_msg}"
						)
			except Exception as e:
				logger.error(
						f"Release mcp server {self.name} to Nacos Failed,try to update it")
				raise RuntimeError(
						f"Release mcp server {self.name} to Nacos Failed")
			if self._nacos_settings.SERVICE_REGISTER and (
					self._type == "mcp-sse"
					or self._type == "mcp-streamable"):
				version = metadata.version('nacos-mcp-wrapper-python')
				service_meta_data = {
					"source": f"nacos-mcp-wrapper-python-{version}",
					**self._nacos_settings.SERVICE_META_DATA}
				await self._nacos_naming_service.register_instance(
						request=RegisterInstanceParam(
								group_name="DEFAULT_GROUP" if self._nacos_settings.SERVICE_GROUP is None else self._nacos_settings.SERVICE_GROUP,
								service_name=self.get_register_service_name(),
								ip=self._nacos_settings.SERVICE_IP,
								port=self._nacos_settings.SERVICE_PORT if self._nacos_settings.SERVICE_PORT else port,
								ephemeral=self._nacos_settings.SERVICE_EPHEMERAL,
								metadata=service_meta_data
						)
				)
			await self.subscribe()
			logger.info(
					f"Register to nacos success,{self.name},version:{self.version}")
		except Exception as e:
			logger.error(f"Failed to register MCP server to Nacos: {e}")
