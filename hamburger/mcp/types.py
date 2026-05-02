"""数据类：MCP 服务器配置 / 工具描述。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MCPServerConfig:
    """单个 MCP 服务器的启动配置。"""

    name: str
    command: str = "npx"
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    source: str = "builtin"   # builtin | custom
    description: str = ""
    emoji: str = "🔌"
    category: str = "其他"


@dataclass
class MCPToolInfo:
    """从 MCP 服务器发现的单个工具描述。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    server_id: str
    server_config: MCPServerConfig
