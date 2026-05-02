"""MCPToolInfo → LangChain BaseTool 适配器。"""
from __future__ import annotations

from typing import Any, Optional

from langchain_core.tools import BaseTool

from . import client as _client
from . import manager as _manager


_TOOL_NAME_PREFIX = "mcp__"


def _tool_full_name(server_id: str, tool_name: str) -> str:
    # 替换不允许的字符（防止冒号 / 空格等触发 LLM tool name 限制）
    safe_sid = server_id.replace("-", "_").replace(".", "_")
    safe_tname = tool_name.replace("-", "_").replace(".", "_")
    return f"{_TOOL_NAME_PREFIX}{safe_sid}__{safe_tname}"


def build_tool(server_id: str, tool_name: str) -> Optional[BaseTool]:
    """根据 (server_id, tool_name) 构造一个可挂载到 Agent 的 BaseTool。

    若服务器未安装或对应工具未发现，返回 None。
    """
    install = _manager.get_install_entry(server_id)
    info = _manager.get_tool_info(server_id, tool_name)
    if install is None or info is None:
        return None

    cfg = install["config"]
    env_values = install["env_values"]

    full_name = _tool_full_name(server_id, tool_name)
    desc_prefix = f"[MCP·{cfg.emoji} {cfg.name}] "
    description = desc_prefix + (info.description or f"MCP 工具: {tool_name}")

    class _MCPTool(BaseTool):
        name: str = full_name
        description: str = description

        def _run(self, **kwargs: Any) -> str:
            return _client.call_tool_sync(cfg, env_values, tool_name, kwargs)

        async def _arun(self, **kwargs: Any) -> str:
            return await _client.call_tool(cfg, env_values, tool_name, kwargs)

    return _MCPTool()
