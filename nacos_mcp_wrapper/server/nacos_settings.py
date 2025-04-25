from typing import Optional

from nacos.auth import CredentialsProvider
from pydantic import Field
from pydantic_settings import BaseSettings


class NacosSettings(BaseSettings):

	SERVER_ADDR : str = Field(
			description="nacos server address",
			default="127.0.0.1:8848")

	SERVER_ENDPOINT : Optional[str] = Field(
			description="nacos server endpoint",
			default=None)

	SERVICE_REGISTER : bool = Field(
			description="whether to register service to nacos",
			default=True)
	
	SERVICE_EPHEMERAL : bool = Field(
			description="whether to register service as ephemeral",
			default=True)

	SERVICE_NAMESPACE : str = Field(
			description="nacos service namespace",
			default="public")

	SERVICE_GROUP : str = Field(
			description="nacos service group",
			default="DEFAULT_GROUP")

	SERVICE_IP : Optional[str] = Field(
			description="nacos service ip",
			default=None)

	USERNAME : Optional[str] = Field(
			description="nacos username for authentication",
			default=None)

	PASSWORD : Optional[str] = Field(
			description="nacos password for authentication",
			default=None)

	ACCESS_KEY : Optional[str] = Field(
			description="nacos access key for aliyun ram authentication",
			default=None)

	SECRET_KEY : Optional[str] = Field(
			description="nacos secret key for aliyun ram authentication",
			default=None)

	CREDENTIAL_PROVIDER : Optional[CredentialsProvider] = Field(
			description="nacos credential provider for aliyun authentication",
			default=None)

	APP_CONN_LABELS : Optional[dict] = Field(
			description="nacos connection labels",
			default={})

	class Config:
		env_prefix = "NACOS_MCP_SERVER_"

