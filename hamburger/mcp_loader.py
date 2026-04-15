import asyncio
import json
import subprocess
import sys
from typing import Any, Optional
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool
from pydantic import create_model, Field


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    source: str = "builtin"
    description: str = ""
    emoji: str = "🔌"
    category: str = "其他"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "env": list(self.env.keys()) if self.env else [],
            "source": self.source,
            "description": self.description,
            "emoji": self.emoji,
            "category": self.category,
        }


def _build_name_to_id_map() -> dict[str, str]:
    result = {}
    for sid, cfg in BUILTIN_MCP_SERVERS.items():
        result[cfg.name] = sid
        result[cfg.name.lower()] = sid
    return result


def _resolve_server_id(server_id: str) -> Optional[str]:
    if server_id in BUILTIN_MCP_SERVERS:
        return server_id
    if server_id in _installed_servers:
        return server_id
    name_map = _build_name_to_id_map()
    resolved = name_map.get(server_id) or name_map.get(server_id.lower())
    if resolved:
        return resolved
    for sid, cfg in BUILTIN_MCP_SERVERS.items():
        if cfg.name.lower() == server_id.lower():
            return sid
    return None


@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str
    server_config: MCPServerConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "server_name": self.server_name,
            "server_emoji": self.server_config.emoji,
        }


_installed_servers: dict[str, MCPServerConfig] = {}
_discovered_tools: dict[str, list[MCPToolInfo]] = {}


BUILTIN_MCP_SERVERS: dict[str, MCPServerConfig] = {
    "filesystem": MCPServerConfig(
        name="Filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "."],
        description="文件系统操作：读写文件、浏览目录",
        emoji="📁",
        category="文件操作",
        source="builtin",
    ),
    "github": MCPServerConfig(
        name="GitHub",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        description="GitHub API 集成：管理仓库、Issues、PR",
        emoji="🐙",
        category="开发工具",
        source="builtin",
    ),
    "postgres": MCPServerConfig(
        name="PostgreSQL",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres"],
        env={"POSTGRES_CONNECTION_STRING": ""},
        description="PostgreSQL 数据库操作",
        emoji="🐘",
        category="数据库",
        source="builtin",
    ),
    "brave-search": MCPServerConfig(
        name="Brave Search",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env={"BRAVE_API_KEY": ""},
        description="Brave 搜索引擎集成",
        emoji="🔍",
        category="搜索",
        source="builtin",
    ),
    "fetch": MCPServerConfig(
        name="Fetch",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-fetch"],
        description="HTTP 请求工具：获取网页内容",
        emoji="📡",
        category="网络",
        source="builtin",
    ),
    "memory": MCPServerConfig(
        name="Memory",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-memory"],
        description="知识图谱记忆系统",
        emoji="🧠",
        category="记忆",
        source="builtin",
    ),
    "sqlite": MCPServerConfig(
        name="SQLite",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sqlite", "--db-path", ":memory:"],
        description="SQLite 数据库操作",
        emoji="🗄️",
        category="数据库",
        source="builtin",
    ),
    "puppeteer": MCPServerConfig(
        name="Puppeteer",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
        description="浏览器自动化",
        emoji="🌐",
        category="浏览器",
        source="builtin",
    ),
    "sequential-thinking": MCPServerConfig(
        name="Sequential Thinking",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        description="结构化思维链推理",
        emoji="🤔",
        category="推理",
        source="builtin",
    ),
    "slack": MCPServerConfig(
        name="Slack",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env={"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
        description="Slack 消息管理",
        emoji="💬",
        category="通讯",
        source="builtin",
    ),
}


def get_builtin_servers() -> list[dict[str, Any]]:
    return [cfg.to_dict() for cfg in BUILTIN_MCP_SERVERS.values()]


def get_installed_servers() -> list[dict[str, Any]]:
    return [cfg.to_dict() for cfg in _installed_servers.values()]


def install_server(
    server_id: str,
    env_values: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    if server_id in BUILTIN_MCP_SERVERS:
        config = BUILTIN_MCP_SERVERS[server_id]
    elif server_id in _installed_servers:
        config = _installed_servers[server_id]
    else:
        return {"success": False, "error": f"未找到 MCP 服务器: {server_id}"}

    if env_values:
        for k, v in env_values.items():
            if k in config.env:
                config.env[k] = v

    missing = [k for k, v in config.env.items() if not v]
    if missing:
        return {
            "success": False,
            "error": f"缺少必要的环境变量: {', '.join(missing)}",
            "missing_env": missing,
        }

    _installed_servers[server_id] = config
    return {
        "success": True,
        "message": f"MCP 服务器 {config.name} 已安装",
        "server": config.to_dict(),
    }


def uninstall_server(server_id: str) -> dict[str, Any]:
    if server_id in _installed_servers:
        config = _installed_servers.pop(server_id)
        _discovered_tools.pop(server_id, None)
        return {
            "success": True,
            "message": f"MCP 服务器 {config.name} 已卸载",
        }
    return {"success": False, "error": f"服务器 {server_id} 未安装"}


async def _discover_tools_from_server(
    config: MCPServerConfig, timeout: float = 15.0
) -> list[MCPToolInfo]:
    tools = []

    try:
        import os

        env = {**os.environ, **config.env}

        proc = await asyncio.create_subprocess_exec(
            config.command,
            *config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "hamburger-agent", "version": "1.0.0"},
            },
        }

        init_json = json.dumps(init_request) + "\n"
        proc.stdin.write(init_json.encode())
        await proc.stdin.drain()

        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            _init_resp = json.loads(line.decode().strip())
        except asyncio.TimeoutError:
            pass

        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }

        tools_json = json.dumps(tools_request) + "\n"
        proc.stdin.write(tools_json.encode())
        await proc.stdin.drain()

        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            tools_resp = json.loads(line.decode().strip())
            tool_list = tools_resp.get("result", {}).get("tools", [])
            for t in tool_list:
                tools.append(
                    MCPToolInfo(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        server_name=config.name,
                        server_config=config,
                    )
                )
        except asyncio.TimeoutError:
            pass

        proc.terminate()
        await proc.wait()

    except FileNotFoundError:
        tools.append(
            MCPToolInfo(
                name=f"{config.name}_unavailable",
                description=f"[需要安装 {config.command}] {config.description}",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "输入参数",
                        }
                    },
                },
                server_name=config.name,
                server_config=config,
            )
        )
    except Exception as e:
        print(f"[MCP Loader] Failed to discover tools from {config.name}: {e}")

    return tools


async def discover_tools(server_id: str) -> list[dict[str, Any]]:
    config = _installed_servers.get(server_id) or BUILTIN_MCP_SERVERS.get(server_id)
    if not config:
        return []

    tools = await _discover_tools_from_server(config)
    _discovered_tools[server_id] = tools
    return [t.to_dict() for t in tools]


async def discover_all_installed_tools() -> list[dict[str, Any]]:
    all_tools = []
    for sid in list(_installed_servers.keys()):
        tools = await discover_tools(sid)
        all_tools.extend(tools)
    return all_tools


def _schema_to_pydantic(schema: dict[str, Any]) -> type:
    fields = {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    type_map = {
        "string": (str, ...),
        "integer": (int, ...),
        "number": (float, ...),
        "boolean": (bool, ...),
        "array": (list, ...),
    }

    for prop_name, prop_schema in properties.items():
        py_type_info = type_map.get(prop_schema.get("type", "string"), (str, ...))
        py_type = py_type_info[0]
        desc = prop_schema.get("description", "")
        default = ... if prop_name in required else None
        fields[prop_name] = (py_type, Field(default=default, description=desc))

    if not fields:
        fields["_placeholder"] = (str, Field(default="", description="No input needed"))

    return create_model("DynamicInput", **fields)


def create_langchain_tool(tool_info: MCPToolInfo) -> BaseTool:
    from langchain_core.tools import StructuredTool

    input_model = _schema_to_pydantic(tool_info.input_schema)

    async def _arun(**kwargs):
        return f"[MCP] 调用 {tool_info.name}({kwargs}) — 需要连接到 MCP 服务器 {tool_info.server_name}"

    def _run(**kwargs):
        return f"[MCP] 调用 {tool_info.name}({kwargs}) — 需要连接到 MCP 服务器 {tool_info.server_name}"

    return StructuredTool(
        name=f"mcp_{tool_info.server_name}_{tool_info.name}",
        description=f"[{tool_info.server_config.emoji} {tool_info.server_name}] {tool_info.description}",
        func=_run,
        coroutine=_arun,
        args_schema=input_model,
    )


def get_langchain_tools_for_server(server_id: str) -> list[BaseTool]:
    tools_info = _discovered_tools.get(server_id, [])
    return [create_langchain_tool(t) for t in tools_info]


def get_all_langchain_tools() -> list[BaseTool]:
    all_tools = []
    for sid in _installed_servers:
        all_tools.extend(get_langchain_tools_for_server(sid))
    return all_tools


def add_custom_server(
    server_id: str,
    name: str,
    command: str,
    args: list[str],
    env: Optional[dict[str, str]] = None,
    description: str = "",
    emoji: str = "🔌",
    category: str = "自定义",
) -> dict[str, Any]:
    config = MCPServerConfig(
        name=name,
        command=command,
        args=args,
        env=env or {},
        description=description,
        emoji=emoji,
        category=category,
        source="custom",
    )
    _installed_servers[server_id] = config
    return {"success": True, "message": f"自定义 MCP 服务器 {name} 已添加"}
