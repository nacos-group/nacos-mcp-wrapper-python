import asyncio
import socket
import threading
from enum import Enum
import json

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

def compare(origin: str, target: str) -> bool:
	try:
		origin_node = json.loads(origin)
		target_node = json.loads(target)
		return compare_nodes(origin_node, target_node)
	except Exception as e:
		print(e)
		return False


def compare_nodes(origin_node, target_node) -> bool:
	if origin_node is None and target_node is None:
		return True
	if origin_node is None or target_node is None:
		return False

	origin_properties = origin_node.get("properties")
	target_properties = target_node.get("properties")

	if (origin_properties is None and target_properties is not None) or (
		origin_properties is not None and target_properties is None
	):
		return False

	if origin_properties is not None and target_properties is not None:
		# 遍历原始 properties
		for key, value_node in origin_properties.items():
			if not isinstance(value_node, dict):
				continue  # 只处理 object 类型

			type_node = value_node.get("type")
			if not isinstance(type_node, str):
				continue

			type_ = type_node

			if key not in target_properties:
				return False

			target_value_node = target_properties[key]
			target_type_node = target_value_node.get("type")
			target_type = target_type_node if isinstance(target_type_node, str) else ""

			if type_ != target_type:
				return False

			# 如果是 object 类型，递归比较
			if type_ == "object":
				if not compare_nodes(value_node, target_value_node):
					return False
			# 如果是 array 类型，比较 items 内容
			elif type_ == "array":
				origin_items = value_node.get("items")
				target_items = target_value_node.get("items")
				if origin_items is not None and target_items is not None:
					if not compare_nodes(origin_items, target_items):
						return False

		# 检查新增字段
		for key in target_properties:
			if key not in origin_properties:
				return False

	origin_required = origin_node.get("required")
	target_required = target_node.get("required")

	if origin_required is not None and target_required is not None:
		if not isinstance(origin_required, list) or not isinstance(target_required, list):
			return False
		if len(origin_required) != len(target_required):
			return False

		origin_set = set()
		for node in origin_required:
			if isinstance(node, str):
				origin_set.add(node)
			else:
				return False

		target_set = set()
		for node in target_required:
			if isinstance(node, str):
				target_set.add(node)
			else:
				return False

		return origin_set == target_set
	else:
		return origin_required is None and target_required is None