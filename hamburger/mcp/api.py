"""FastAPI 路由：所有 /api/mcp/* 端点集中在此。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import manager as _manager


mcp_router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ─────────────────────────────────────────────
#  请求模型
# ─────────────────────────────────────────────

class _InstallRequest(BaseModel):
    server_id: str
    env_values: Dict[str, str] = {}


class _UninstallRequest(BaseModel):
    server_id: str


class _CustomServerRequest(BaseModel):
    server_id: str
    name: str
    command: str = "npx"
    args: List[str] = []
    env: Dict[str, str] = {}
    description: str = ""
    emoji: str = "⚡"
    category: str = "自定义"


# ─────────────────────────────────────────────
#  服务器管理端点
# ─────────────────────────────────────────────

@mcp_router.get("/servers/builtin")
def list_builtin() -> Dict[str, Any]:
    """目录中的所有服务器（内置 + 自定义）。"""
    return {"servers": _manager.list_builtin()}


@mcp_router.get("/servers/installed")
def list_installed() -> Dict[str, Any]:
    return {"servers": _manager.list_installed()}


@mcp_router.post("/servers/install")
def install(req: _InstallRequest) -> Dict[str, Any]:
    result = _manager.install_server(req.server_id, req.env_values)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@mcp_router.post("/servers/uninstall")
def uninstall(req: _UninstallRequest) -> Dict[str, Any]:
    result = _manager.uninstall_server(req.server_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@mcp_router.post("/servers/{server_id}/discover")
async def discover(server_id: str) -> Dict[str, Any]:
    """启动 MCP 子进程发现工具列表（IO-bound，可能耗时）。"""
    return await _manager.discover_tools(server_id)


@mcp_router.post("/servers/custom")
def add_custom(req: _CustomServerRequest) -> Dict[str, Any]:
    result = _manager.add_custom(
        server_id=req.server_id,
        name=req.name,
        command=req.command,
        args=req.args,
        env=req.env,
        description=req.description,
        emoji=req.emoji,
        category=req.category,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ─────────────────────────────────────────────
#  工具池端点（供生菜面板）
# ─────────────────────────────────────────────

@mcp_router.get("/tools")
def list_tools() -> Dict[str, Any]:
    """返回所有已发现的 MCP 工具（扁平池）。"""
    return {"tools": _manager.get_tool_pool()}
