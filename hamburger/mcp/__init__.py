"""hamburger.mcp — 独立的 MCP 服务模块

职责边界：仅与生菜（Lettuce）组件挂钩，不依赖 Agent / Recipe / Burger。
对外公开纯函数 API + 一个 FastAPI APIRouter。
"""
from __future__ import annotations

from .types import MCPServerConfig, MCPToolInfo
from .catalog import (
    BUILTIN_MCP_SERVERS,
    add_custom_server,
    get_server_config,
    iter_all_servers,
)
from .manager import (
    bootstrap,
    install_server,
    uninstall_server,
    list_builtin,
    list_installed,
    get_tool_pool,
    get_tool_info,
    discover_tools,
)
from .adapter import build_tool
from .api import mcp_router

__all__ = [
    "MCPServerConfig",
    "MCPToolInfo",
    "BUILTIN_MCP_SERVERS",
    "bootstrap",
    "install_server",
    "uninstall_server",
    "list_builtin",
    "list_installed",
    "get_tool_pool",
    "get_tool_info",
    "discover_tools",
    "build_tool",
    "add_custom_server",
    "get_server_config",
    "iter_all_servers",
    "mcp_router",
]
