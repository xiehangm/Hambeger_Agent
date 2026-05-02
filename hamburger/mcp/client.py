"""MCP JSON-RPC stdio 客户端。

封装了对 MCP 服务器子进程的两类调用：
  * discover(cfg, env_values)       -> tools/list
  * call_tool(cfg, env_values, ...) -> tools/call
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from typing import Any, Dict, List

from .types import MCPServerConfig, MCPToolInfo


# ─────────────────────────────────────────────
#  JSON-RPC 报文构造
# ─────────────────────────────────────────────

def _init_msg() -> str:
    return json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hamburger-agent", "version": "1.0.0"},
        },
    })


def _list_msg() -> str:
    return json.dumps({
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/list",
        "params": {},
    })


def _call_msg(tool_name: str, arguments: Dict[str, Any]) -> str:
    return json.dumps({
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    })


def _merge_env(cfg: MCPServerConfig, env_values: Dict[str, str]) -> Dict[str, str]:
    """把 cfg.env 中声明的键用 env_values 中真实值覆盖，再合并到 os.environ。"""
    overrides = {k: env_values.get(k, v) for k, v in cfg.env.items()}
    return {**os.environ, **overrides}


def _parse_response(stdout_text: str, target_id: int) -> Dict[str, Any] | None:
    for line in stdout_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            resp = json.loads(line)
        except json.JSONDecodeError:
            continue
        if resp.get("id") == target_id:
            return resp
    return None


def _extract_text(result: Dict[str, Any]) -> str:
    content = result.get("content") or []
    parts = [c.get("text", "") for c in content if c.get("type") == "text"]
    return "\n".join(parts) if parts else str(result)


# ─────────────────────────────────────────────
#  工具发现（异步）
# ─────────────────────────────────────────────

async def discover(
    cfg: MCPServerConfig,
    env_values: Dict[str, str],
    server_id: str,
    timeout: float = 15.0,
) -> List[MCPToolInfo]:
    """启动 MCP 子进程并请求 tools/list。"""
    merged_env = _merge_env(cfg, env_values)
    stdin_data = (_init_msg() + "\n" + _list_msg() + "\n").encode()

    proc = await asyncio.create_subprocess_exec(
        cfg.command, *cfg.args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=merged_env,
    )
    stdout_data, _ = await asyncio.wait_for(
        proc.communicate(stdin_data), timeout=timeout
    )

    resp = _parse_response(stdout_data.decode(errors="replace"), 2)
    discovered: List[MCPToolInfo] = []
    if resp and "result" in resp:
        for t in resp["result"].get("tools", []):
            discovered.append(MCPToolInfo(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                server_id=server_id,
                server_config=cfg,
            ))
    return discovered


# ─────────────────────────────────────────────
#  工具调用
# ─────────────────────────────────────────────

async def call_tool(
    cfg: MCPServerConfig,
    env_values: Dict[str, str],
    tool_name: str,
    arguments: Dict[str, Any],
    timeout: float = 30.0,
) -> str:
    merged_env = _merge_env(cfg, env_values)
    stdin_data = (_init_msg() + "\n" +
                  _call_msg(tool_name, arguments) + "\n").encode()

    try:
        proc = await asyncio.create_subprocess_exec(
            cfg.command, *cfg.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        stdout_data, _ = await asyncio.wait_for(
            proc.communicate(stdin_data), timeout=timeout
        )
    except asyncio.TimeoutError:
        return "[MCP] 调用超时"
    except FileNotFoundError as exc:
        return f"[MCP] 命令不存在: {exc}"
    except Exception as exc:  # pragma: no cover - 防御性
        return f"[MCP] 调用失败: {exc}"

    resp = _parse_response(stdout_data.decode(errors="replace"), 2)
    if not resp:
        return "[MCP] 无返回内容"
    if "error" in resp:
        err = resp["error"]
        return f"[MCP Error] {err.get('message', str(err))}"
    return _extract_text(resp.get("result") or {})


def call_tool_sync(
    cfg: MCPServerConfig,
    env_values: Dict[str, str],
    tool_name: str,
    arguments: Dict[str, Any],
    timeout: float = 30.0,
) -> str:
    """同步版本，供 LangChain BaseTool._run 使用。"""
    merged_env = _merge_env(cfg, env_values)
    stdin_text = _init_msg() + "\n" + _call_msg(tool_name, arguments) + "\n"
    try:
        result = subprocess.run(
            [cfg.command] + list(cfg.args),
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return "[MCP] 调用超时"
    except FileNotFoundError as exc:
        return f"[MCP] 命令不存在: {exc}"
    except Exception as exc:  # pragma: no cover - 防御性
        return f"[MCP] 调用失败: {exc}"

    resp = _parse_response(result.stdout, 2)
    if not resp:
        return "[MCP] 无返回内容"
    if "error" in resp:
        err = resp["error"]
        return f"[MCP Error] {err.get('message', str(err))}"
    return _extract_text(resp.get("result") or {})
