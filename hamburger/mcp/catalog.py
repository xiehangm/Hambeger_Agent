"""内置 MCP 服务器目录 + 自定义注册。

模块层维护两个字典：内置（只读）与自定义（运行期可加）。
"""
from __future__ import annotations

from typing import Dict, Iterator, Optional, Tuple

from .types import MCPServerConfig


# ─────────────────────────────────────────────
#  内置服务器目录
# ─────────────────────────────────────────────
BUILTIN_MCP_SERVERS: Dict[str, MCPServerConfig] = {
    "filesystem": MCPServerConfig(
        name="文件系统",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "."],
        description="读写本地文件与目录，支持递归遍历、搜索内容",
        emoji="📁",
        category="文件操作",
    ),
    "fetch": MCPServerConfig(
        name="网络请求",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-fetch"],
        description="抓取 URL 内容，返回 Markdown / 原始 HTML",
        emoji="📡",
        category="网络",
    ),
    "memory": MCPServerConfig(
        name="记忆存储",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-memory"],
        description="跨会话持久化键值记忆，存储 Agent 状态",
        emoji="🧠",
        category="记忆",
    ),
    "sqlite": MCPServerConfig(
        name="SQLite 数据库",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sqlite",
              "--db-path", ":memory:"],
        description="运行 SQL 查询，读写 SQLite 数据库",
        emoji="🗄️",
        category="数据库",
    ),
    "puppeteer": MCPServerConfig(
        name="Puppeteer 浏览器",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
        description="无头浏览器自动化：截图、点击、表单填写",
        emoji="🌐",
        category="浏览器",
    ),
    "github": MCPServerConfig(
        name="GitHub",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        description="GitHub 仓库操作：读取文件、搜索代码、创建 Issue",
        emoji="🐙",
        category="开发工具",
    ),
    "postgres": MCPServerConfig(
        name="PostgreSQL",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres"],
        env={"POSTGRES_CONNECTION_STRING": ""},
        description="连接 PostgreSQL 数据库，执行 SQL 查询",
        emoji="🐘",
        category="数据库",
    ),
    "brave-search": MCPServerConfig(
        name="Brave 搜索",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env={"BRAVE_API_KEY": ""},
        description="通过 Brave Search API 搜索互联网内容",
        emoji="🔍",
        category="搜索",
    ),
    "sequential-thinking": MCPServerConfig(
        name="链式思考",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        description="结构化多步推理工具，帮助 Agent 拆解复杂任务",
        emoji="🤔",
        category="推理",
    ),
    "slack": MCPServerConfig(
        name="Slack",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env={"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
        description="发送消息、读取频道、管理 Slack 工作区",
        emoji="💬",
        category="通讯",
    ),
}


# ─────────────────────────────────────────────
#  自定义服务器目录（运行期 + 持久化恢复）
# ─────────────────────────────────────────────
_CUSTOM_SERVERS: Dict[str, MCPServerConfig] = {}


def add_custom_server(
    server_id: str,
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    description: str = "",
    emoji: str = "⚡",
    category: str = "自定义",
) -> MCPServerConfig:
    """注册一个自定义 MCP 服务器到目录中（不立即安装）。"""
    cfg = MCPServerConfig(
        name=name,
        command=command,
        args=list(args or []),
        env=dict(env or {}),
        source="custom",
        description=description,
        emoji=emoji,
        category=category,
    )
    _CUSTOM_SERVERS[server_id] = cfg
    return cfg


def remove_custom_server(server_id: str) -> bool:
    return _CUSTOM_SERVERS.pop(server_id, None) is not None


def get_server_config(server_id: str) -> Optional[MCPServerConfig]:
    """按 id 查找服务器配置（先内置后自定义）。"""
    return BUILTIN_MCP_SERVERS.get(server_id) or _CUSTOM_SERVERS.get(server_id)


def iter_all_servers() -> Iterator[Tuple[str, MCPServerConfig]]:
    """遍历所有目录服务器（内置 + 自定义）。"""
    yield from BUILTIN_MCP_SERVERS.items()
    yield from _CUSTOM_SERVERS.items()


def custom_catalog_snapshot() -> Dict[str, Dict[str, object]]:
    """把当前自定义目录序列化为可持久化字典。"""
    return {
        sid: {
            "name": cfg.name,
            "command": cfg.command,
            "args": list(cfg.args),
            "env": dict(cfg.env),
            "description": cfg.description,
            "emoji": cfg.emoji,
            "category": cfg.category,
        }
        for sid, cfg in _CUSTOM_SERVERS.items()
    }


def restore_custom_catalog(snapshot: Dict[str, Dict[str, object]]) -> None:
    """从持久化快照恢复自定义目录。"""
    _CUSTOM_SERVERS.clear()
    for sid, data in (snapshot or {}).items():
        try:
            add_custom_server(
                server_id=sid,
                name=str(data.get("name") or sid),
                command=str(data.get("command") or "npx"),
                args=list(data.get("args") or []),  # type: ignore[arg-type]
                env=dict(data.get("env") or {}),    # type: ignore[arg-type]
                description=str(data.get("description") or ""),
                emoji=str(data.get("emoji") or "⚡"),
                category=str(data.get("category") or "自定义"),
            )
        except Exception as exc:  # pragma: no cover - 防御性
            print(f"[MCP] 跳过损坏的自定义条目 {sid}: {exc}")
