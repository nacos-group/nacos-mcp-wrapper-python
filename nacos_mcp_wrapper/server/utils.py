import asyncio
import socket
import threading
from enum import Enum

import jsonref
import psutil

def get_first_non_loopback_ip():
	for interface, addrs in psutil.net_if_addrs().items():
		for addr in addrs:
			if addr.family == socket.AF_INET and not addr.address.startswith(
					'127.'):
				return addr.address
	return None

def jsonref_default(obj):
	if isinstance(obj, jsonref.JsonRef):
		return obj.__subject__
	raise TypeError(
			f"Object of type {obj.__class__.__name__} is not JSON serializable")

class ConfigSuffix(Enum):
	TOOLS = "-mcp-tools.json"
	PROMPTS = "-mcp-prompt.json"
	RESOURCES = "-mcp-resource.json"
	MCP_SERVER = "-mcp-server.json"