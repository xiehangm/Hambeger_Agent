"""
hamburger/mcp_loader.py
=======================
MCP (Model Context Protocol) 服务器管理与工具加载模块。

职责：
- 维护内置 MCP 服务器目录（BUILTIN_MCP_SERVERS）
- 会话级状态：已安装服务器 + 工具发现缓存
- 提供安装/卸载/发现工具的 API
- 将 MCP 工具 / CLI 命令生成 LangChain BaseTool 对象
"""

from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool


# ─────────────────────────────────────────────
#  数据结构
# ─────────────────────────────────────────────

@dataclass
class MCPServerConfig:
    name: str
    command: str = "npx"
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    source: str = "builtin"
    description: str = ""
    emoji: str = "🔌"
    category: str = "其他"


@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    server_config: MCPServerConfig


# ─────────────────────────────────────────────
#  内置 MCP 服务器目录
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
#  会话级状态（内存存储）
# ─────────────────────────────────────────────

# { server_id: { "config": MCPServerConfig, "env_values": dict } }
_installed_servers: Dict[str, Dict[str, Any]] = {}

# { server_id: [ MCPToolInfo, ... ] }
_discovered_tools_cache: Dict[str, List[MCPToolInfo]] = {}


# ─────────────────────────────────────────────
#  服务器管理 API
# ─────────────────────────────────────────────

def install_server(server_id: str, env_values: Dict[str, str]) -> Dict[str, Any]:
    """注册一个 MCP 服务器（内存级安装，不启动子进程）。"""
    if server_id not in BUILTIN_MCP_SERVERS:
        return {"success": False, "error": f"未知服务器 ID: {server_id}"}

    config = BUILTIN_MCP_SERVERS[server_id]
    _installed_servers[server_id] = {
        "config": config, "env_values": env_values}
    # 清除旧缓存以便重新发现
    _discovered_tools_cache.pop(server_id, None)

    print(f"[MCP] 已安装: {config.name} ({server_id})")
    return {"success": True, "server_id": server_id, "name": config.name}


def uninstall_server(server_id: str) -> Dict[str, Any]:
    """注销一个已安装的 MCP 服务器。"""
    if server_id not in _installed_servers:
        return {"success": False, "error": f"服务器未安装: {server_id}"}

    _installed_servers.pop(server_id)
    _discovered_tools_cache.pop(server_id, None)
    print(f"[MCP] 已卸载: {server_id}")
    return {"success": True}


def get_installed_servers() -> List[Dict[str, Any]]:
    """返回已安装的服务器列表（含已发现工具）。"""
    result = []
    for sid, data in _installed_servers.items():
        cfg: MCPServerConfig = data["config"]
        tools = _discovered_tools_cache.get(sid, [])
        result.append({
            "id": sid,
            "name": cfg.name,
            "emoji": cfg.emoji,
            "category": cfg.category,
            "description": cfg.description,
            "tools": [
                {"name": t.name, "description": t.description}
                for t in tools
            ],
            "tools_discovered": sid in _discovered_tools_cache,
        })
    return result


def get_builtin_servers() -> List[Dict[str, Any]]:
    """返回所有内置服务器的摘要信息供前端展示。"""
    result = []
    for sid, cfg in BUILTIN_MCP_SERVERS.items():
        result.append({
            "id": sid,
            "name": cfg.name,
            "emoji": cfg.emoji,
            "category": cfg.category,
            "description": cfg.description,
            "env_keys": list(cfg.env.keys()),
            "installed": sid in _installed_servers,
        })
    return result


# ─────────────────────────────────────────────
#  工具发现（异步，启动 MCP 子进程）
# ─────────────────────────────────────────────

async def discover_tools(server_id: str) -> Dict[str, Any]:
    """
    启动 MCP 服务器子进程，发送 tools/list JSON-RPC 请求，
    解析并缓存工具列表。子进程不可用时返回 graceful 错误。
    """
    if server_id not in _installed_servers:
        return {"success": False, "error": "服务器未安装", "tools": []}

    # 命中缓存则直接返回
    if server_id in _discovered_tools_cache:
        tools = _discovered_tools_cache[server_id]
        return {
            "success": True,
            "tools": [{"name": t.name, "description": t.description} for t in tools],
        }

    data = _installed_servers[server_id]
    cfg: MCPServerConfig = data["config"]
    env_values: Dict[str, str] = data["env_values"]

    # 合并环境变量
    import os
    merged_env = {**os.environ, **
                  {k: env_values.get(k, v) for k, v in cfg.env.items()}}

    try:
        # JSON-RPC 初始化消息
        init_msg = json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "hamburger-agent", "version": "1.0.0"},
            },
        })
        list_msg = json.dumps({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/list",
            "params": {},
        })

        proc = await asyncio.create_subprocess_exec(
            cfg.command, *cfg.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )

        # 写入两条 JSON-RPC 请求（换行分隔）
        stdin_data = (init_msg + "\n" + list_msg + "\n").encode()
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(stdin_data),
            timeout=15.0,
        )

        # 解析 stdout，找到 tools/list 的响应
        discovered: List[MCPToolInfo] = []
        for line in stdout_data.decode(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if resp.get("id") == 2 and "result" in resp:
                for t in resp["result"].get("tools", []):
                    discovered.append(MCPToolInfo(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        server_name=server_id,
                        server_config=cfg,
                    ))
                break

        _discovered_tools_cache[server_id] = discovered
        print(f"[MCP] 发现 {len(discovered)} 个工具 from {server_id}")
        return {
            "success": True,
            "tools": [{"name": t.name, "description": t.description} for t in discovered],
        }

    except asyncio.TimeoutError:
        return {"success": False, "error": "MCP 服务器启动超时（请确认 npx 可用）", "tools": []}
    except FileNotFoundError:
        return {"success": False, "error": f"命令不存在: {cfg.command}（请安装 Node.js / npx）", "tools": []}
    except Exception as exc:
        return {"success": False, "error": str(exc), "tools": []}


# ─────────────────────────────────────────────
#  工具工厂：MCP 工具 → LangChain BaseTool
# ─────────────────────────────────────────────

def create_langchain_tool(tool_info: MCPToolInfo) -> BaseTool:
    """将 MCPToolInfo 封装为 LangChain BaseTool（通过子进程 JSON-RPC 调用）。"""
    cfg = tool_info.server_config
    tool_name = tool_info.name

    class _MCPTool(BaseTool):
        name: str = tool_info.name
        description: str = tool_info.description or f"MCP 工具: {tool_info.name}"

        def _run(self, **kwargs: Any) -> str:
            return _call_mcp_tool_sync(cfg, tool_name, kwargs)

        async def _arun(self, **kwargs: Any) -> str:
            return await _call_mcp_tool_async(cfg, tool_name, kwargs)

    return _MCPTool()


def _call_mcp_tool_sync(cfg: MCPServerConfig, tool_name: str, arguments: Dict[str, Any]) -> str:
    """同步调用 MCP 工具（启动子进程，发送单次 tool/call 请求）。"""
    import os
    merged_env = {**os.environ, **{k: "" for k in cfg.env}}

    init_msg = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hamburger-agent", "version": "1.0.0"},
        },
    })
    call_msg = json.dumps({
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    })

    try:
        result = subprocess.run(
            [cfg.command] + cfg.args,
            input=(init_msg + "\n" + call_msg + "\n"),
            capture_output=True,
            text=True,
            timeout=30,
            env=merged_env,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if resp.get("id") == 2:
                if "result" in resp:
                    content = resp["result"].get("content", [])
                    parts = [c.get("text", "")
                             for c in content if c.get("type") == "text"]
                    return "\n".join(parts) if parts else str(resp["result"])
                if "error" in resp:
                    return f"[MCP Error] {resp['error'].get('message', str(resp['error']))}"
        return "[MCP] 无返回内容"
    except subprocess.TimeoutExpired:
        return "[MCP] 调用超时"
    except Exception as exc:
        return f"[MCP] 调用失败: {exc}"


async def _call_mcp_tool_async(cfg: MCPServerConfig, tool_name: str, arguments: Dict[str, Any]) -> str:
    import os
    merged_env = {**os.environ, **{k: "" for k in cfg.env}}

    init_msg = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hamburger-agent", "version": "1.0.0"},
        },
    })
    call_msg = json.dumps({
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    })

    try:
        proc = await asyncio.create_subprocess_exec(
            cfg.command, *cfg.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        stdin_data = (init_msg + "\n" + call_msg + "\n").encode()
        stdout_data, _ = await asyncio.wait_for(proc.communicate(stdin_data), timeout=30.0)

        for line in stdout_data.decode(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if resp.get("id") == 2:
                if "result" in resp:
                    content = resp["result"].get("content", [])
                    parts = [c.get("text", "")
                             for c in content if c.get("type") == "text"]
                    return "\n".join(parts) if parts else str(resp["result"])
                if "error" in resp:
                    return f"[MCP Error] {resp['error'].get('message', str(resp['error']))}"
        return "[MCP] 无返回内容"
    except asyncio.TimeoutError:
        return "[MCP] 调用超时"
    except Exception as exc:
        return f"[MCP] 调用失败: {exc}"


# ─────────────────────────────────────────────
#  工具工厂：CLI 命令 → LangChain BaseTool
# ─────────────────────────────────────────────

def create_cli_tool(name: str, description: str, command_template: str) -> BaseTool:
    """
    将 Shell 命令模板封装为 LangChain BaseTool。
    命令中的 {input} 占位符会被工具输入替换。
    """
    class _CLITool(BaseTool):
        name: str = name
        description: str = description or f"CLI 工具: {name}"

        def _run(self, input: str = "", **kwargs: Any) -> str:
            # 替换占位符，防止 shell 注入（使用列表参数，不经过 shell 解释）
            cmd_str = command_template.replace("{input}", input)
            try:
                parts = shlex.split(cmd_str)
                result = subprocess.run(
                    parts,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    shell=False,  # 安全：不使用 shell=True
                )
                output = result.stdout.strip()
                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    return f"[CLI 错误 exit={result.returncode}] {stderr or output}"
                return output if output else "(命令执行成功，无输出)"
            except subprocess.TimeoutExpired:
                return "[CLI] 执行超时"
            except FileNotFoundError as exc:
                return f"[CLI] 命令不存在: {exc}"
            except Exception as exc:
                return f"[CLI] 执行失败: {exc}"

        async def _arun(self, input: str = "", **kwargs: Any) -> str:
            return self._run(input=input, **kwargs)

    return _CLITool()
