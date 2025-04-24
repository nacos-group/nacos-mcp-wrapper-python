from pydantic import BaseModel


class ServiceRef(BaseModel):
	namespaceId: str
	groupName: str
	serviceName: str


class RemoteServerConfig(BaseModel):
	serviceRef: ServiceRef | None = None
	exportPath: str = None


class MCPServerInfo(BaseModel):
	protocol: str
	name: str
	description: str | None = None
	version: str | None = None
	enabled: bool = True
	remoteServerConfig: RemoteServerConfig | None = None
	localServerConfig: dict | None = None
	toolsDescriptionRef: str | None = None
	promptDescriptionRef: str | None = None
	resourceDescriptionRef: str | None = None


class ToolMeta(BaseModel):
	enabled: bool = True
