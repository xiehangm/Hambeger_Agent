"""会话级 MCP 状态管理：已安装服务器 + 工具发现缓存。

所有公开函数均为纯函数风格（无类）；内部状态私有，外部只能通过 API 修改。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from . import catalog as _catalog
from . import store as _store
from .client import discover as _client_discover
from .types import MCPServerConfig, MCPToolInfo


# ─────────────────────────────────────────────
#  私有状态
# ─────────────────────────────────────────────
_installed: Dict[str, Dict[str, Any]] = {}
# value: {"config": MCPServerConfig, "env_values": dict[str, str]}

_tools_cache: Dict[str, List[MCPToolInfo]] = {}

_loaded: bool = False


# ─────────────────────────────────────────────
#  内部辅助
# ─────────────────────────────────────────────

def _persist() -> None:
    _store.save({
        "installed": {
            sid: {"env_values": dict(data["env_values"])}
            for sid, data in _installed.items()
        },
        "custom_catalog": _catalog.custom_catalog_snapshot(),
    })


def _summary(server_id: str, cfg: MCPServerConfig) -> Dict[str, Any]:
    tools = _tools_cache.get(server_id, [])
    return {
        "id": server_id,
        "name": cfg.name,
        "emoji": cfg.emoji,
        "category": cfg.category,
        "description": cfg.description,
        "source": cfg.source,
        "env_keys": list(cfg.env.keys()),
        "tools": [
            {"name": t.name, "description": t.description}
            for t in tools
        ],
        "tools_discovered": server_id in _tools_cache,
        "installed": server_id in _installed,
    }


# ─────────────────────────────────────────────
#  生命周期
# ─────────────────────────────────────────────

def bootstrap() -> None:
    """从持久化文件恢复 installed + custom_catalog。幂等。"""
    global _loaded
    if _loaded:
        return
    data = _store.load()
    _catalog.restore_custom_catalog(data.get("custom_catalog") or {})
    for sid, entry in (data.get("installed") or {}).items():
        cfg = _catalog.get_server_config(sid)
        if cfg is None:
            print(f"[MCP] 跳过孤立的已安装条目: {sid}")
            continue
        _installed[sid] = {
            "config": cfg,
            "env_values": dict(entry.get("env_values") or {}),
        }
    _loaded = True
    print(f"[MCP] bootstrap: {len(_installed)} 个已安装服务器")


# ─────────────────────────────────────────────
#  服务器管理
# ─────────────────────────────────────────────

def install_server(server_id: str, env_values: Dict[str, str]) -> Dict[str, Any]:
    cfg = _catalog.get_server_config(server_id)
    if cfg is None:
        return {"success": False, "error": f"未知服务器 ID: {server_id}"}
    _installed[server_id] = {"config": cfg,
                             "env_values": dict(env_values or {})}
    _tools_cache.pop(server_id, None)
    _persist()
    print(f"[MCP] 已安装: {cfg.name} ({server_id})")
    return {"success": True, "server_id": server_id, "name": cfg.name}


def uninstall_server(server_id: str) -> Dict[str, Any]:
    if server_id not in _installed:
        return {"success": False, "error": f"服务器未安装: {server_id}"}
    _installed.pop(server_id)
    _tools_cache.pop(server_id, None)
    _persist()
    print(f"[MCP] 已卸载: {server_id}")
    return {"success": True}


def add_custom(
    server_id: str,
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    description: str = "",
    emoji: str = "⚡",
    category: str = "自定义",
) -> Dict[str, Any]:
    if _catalog.get_server_config(server_id) is not None:
        return {"success": False, "error": f"服务器 ID 已存在: {server_id}"}
    _catalog.add_custom_server(
        server_id=server_id,
        name=name,
        command=command,
        args=args,
        env=env,
        description=description,
        emoji=emoji,
        category=category,
    )
    _persist()
    return {"success": True, "server_id": server_id}


# ─────────────────────────────────────────────
#  查询
# ─────────────────────────────────────────────

def list_builtin() -> List[Dict[str, Any]]:
    """所有目录服务器（含 installed/source 标记）。"""
    return [
        _summary(sid, cfg)
        for sid, cfg in _catalog.iter_all_servers()
    ]


def list_installed() -> List[Dict[str, Any]]:
    return [
        _summary(sid, data["config"])
        for sid, data in _installed.items()
    ]


def get_tool_pool() -> List[Dict[str, Any]]:
    """已发现的所有 MCP 工具扁平池（供生菜面板）。"""
    pool: List[Dict[str, Any]] = []
    for sid, tools in _tools_cache.items():
        if sid not in _installed:
            continue
        cfg = _installed[sid]["config"]
        for t in tools:
            pool.append({
                "server_id": sid,
                "server_name": cfg.name,
                "server_emoji": cfg.emoji,
                "server_category": cfg.category,
                "tool_name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            })
    return pool


def get_tool_info(server_id: str, tool_name: str) -> Optional[MCPToolInfo]:
    for t in _tools_cache.get(server_id, []):
        if t.name == tool_name:
            return t
    return None


def get_install_entry(server_id: str) -> Optional[Dict[str, Any]]:
    """供 adapter 使用：取回 (config, env_values)；服务器未安装时返回 None。"""
    return _installed.get(server_id)


# ─────────────────────────────────────────────
#  工具发现
# ─────────────────────────────────────────────

async def discover_tools(server_id: str) -> Dict[str, Any]:
    if server_id not in _installed:
        return {"success": False, "error": "服务器未安装", "tools": []}

    if server_id in _tools_cache:
        cached = _tools_cache[server_id]
        return {
            "success": True,
            "tools": [{"name": t.name, "description": t.description} for t in cached],
        }

    data = _installed[server_id]
    cfg: MCPServerConfig = data["config"]
    env_values: Dict[str, str] = data["env_values"]

    try:
        discovered = await _client_discover(cfg, env_values, server_id)
    except asyncio.TimeoutError:
        return {"success": False, "error": "MCP 服务器启动超时（请确认 npx 可用）", "tools": []}
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"命令不存在: {cfg.command}（请安装 Node.js / npx）",
            "tools": [],
        }
    except Exception as exc:  # pragma: no cover - 防御性
        return {"success": False, "error": str(exc), "tools": []}

    _tools_cache[server_id] = discovered
    print(f"[MCP] 发现 {len(discovered)} 个工具 from {server_id}")
    return {
        "success": True,
        "tools": [{"name": t.name, "description": t.description} for t in discovered],
    }
