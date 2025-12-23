import logging
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal, Collection, Callable
from mcp import stdio_server
from mcp.server import FastMCP
from mcp.server.auth.provider import OAuthAuthorizationServerProvider, \
	TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp.server import lifespan_wrapper
from mcp.server.fastmcp.tools import Tool
from mcp.server.lowlevel.server import lifespan as default_lifespan, \
	LifespanResultT
from mcp.server.streamable_http import EventStore
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon

from nacos_mcp_wrapper.server.nacos_server import NacosServer
from nacos_mcp_wrapper.server.nacos_settings import NacosSettings

logger = logging.getLogger(__name__)


class NacosMCP(FastMCP):

	def __init__(self,
			name: str | None = None,
			version: str | None = None,
			nacos_settings: NacosSettings | None = None,
			instructions: str | None = None,
			website_url: str | None = None,
			icons: list[Icon] | None = None,
			auth_server_provider: OAuthAuthorizationServerProvider[
									  Any, Any, Any]
								  | None = None,
			token_verifier: TokenVerifier | None = None,
			event_store: EventStore | None = None,
			retry_interval: int | None = None,
			*,
			tools: list[Tool] | None = None,
			debug: bool = False,
			log_level: Literal[
				"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
			host: str = "127.0.0.1",
			port: int = 8000,
			mount_path: str = "/",
			sse_path: str = "/sse",
			message_path: str = "/messages/",
			streamable_http_path: str = "/mcp",
			json_response: bool = False,
			stateless_http: bool = False,
			warn_on_duplicate_resources: bool = True,
			warn_on_duplicate_tools: bool = True,
			warn_on_duplicate_prompts: bool = True,
			dependencies: Collection[str] = (),
			lifespan: (Callable[[FastMCP[LifespanResultT]],
			AbstractAsyncContextManager[LifespanResultT]] | None) = None,
			auth: AuthSettings | None = None,
			transport_security: TransportSecuritySettings | None = None,
	):
		super().__init__(
				name=name,
				instructions=instructions,
				website_url=website_url,
				icons=icons,
				auth_server_provider=auth_server_provider,
				token_verifier=token_verifier,
				event_store=event_store,
				retry_interval=retry_interval,
				tools=tools,
				debug=debug,
				log_level=log_level,
				host=host,
				port=port,
				mount_path=mount_path,
				sse_path=sse_path,
				message_path=message_path,
				streamable_http_path=streamable_http_path,
				json_response=json_response,
				stateless_http=stateless_http,
				warn_on_duplicate_resources=warn_on_duplicate_resources,
				warn_on_duplicate_tools=warn_on_duplicate_tools,
				warn_on_duplicate_prompts=warn_on_duplicate_prompts,
				dependencies=dependencies,
				lifespan=lifespan,
				auth=auth,
				transport_security=transport_security,
		)

		self._mcp_server = NacosServer(
				name=name or "FastMCP",
				nacos_settings=nacos_settings,
				version=version,
				instructions=instructions,
				website_url=website_url,
				icons=icons,
				lifespan=lifespan_wrapper(self, self.settings.lifespan)
				if self.settings.lifespan
				else default_lifespan,
		)
		# Set up MCP protocol handlers
		self._setup_handlers()

	async def run_stdio_async(self) -> None:
		"""Run the server using stdio transport."""
		async with stdio_server() as (read_stream, write_stream):
			await self._mcp_server.register_to_nacos("stdio")
			await self._mcp_server.run(
					read_stream,
					write_stream,
					self._mcp_server.create_initialization_options(),
			)

	async def run_sse_async(self, mount_path: str | None = None) -> None:
		"""Run the server using SSE transport."""
		import uvicorn

		starlette_app = self.sse_app(mount_path)
		await self._mcp_server.register_to_nacos("sse", self.settings.port,
												 self.settings.sse_path)
		config = uvicorn.Config(
				starlette_app,
				host=self.settings.host,
				port=self.settings.port,
				log_level=self.settings.log_level.lower(),
		)
		server = uvicorn.Server(config)
		await server.serve()

	async def run_streamable_http_async(self) -> None:
		"""Run the server using StreamableHTTP transport."""
		import uvicorn

		starlette_app = self.streamable_http_app()
		await self._mcp_server.register_to_nacos("streamable-http",
												 self.settings.port,
												 self.settings.streamable_http_path)
		config = uvicorn.Config(
				starlette_app,
				host=self.settings.host,
				port=self.settings.port,
				log_level=self.settings.log_level.lower(),
		)
		server = uvicorn.Server(config)
		await server.serve()
