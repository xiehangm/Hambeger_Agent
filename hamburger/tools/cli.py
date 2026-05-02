"""CLI 工具：把 Shell 命令封装为 LangChain BaseTool。

从原 hamburger/mcp_loader.py 迁出，与 MCP 解耦。
"""
from __future__ import annotations

import shlex
import subprocess
from typing import Any

from langchain_core.tools import BaseTool


def create_cli_tool(name: str, description: str, command_template: str) -> BaseTool:
    """将 Shell 命令模板封装为 LangChain BaseTool。

    命令中的 ``{input}`` 占位符会被工具输入替换；命令以列表参数启动，
    不经过 shell 解释，避免注入。
    """
    _name = name
    _description = description or f"CLI 工具: {name}"
    _template = command_template

    class _CLITool(BaseTool):
        name: str = _name
        description: str = _description

        def _run(self, input: str = "", **kwargs: Any) -> str:
            cmd_str = _template.replace("{input}", input)
            try:
                parts = shlex.split(cmd_str)
                result = subprocess.run(
                    parts,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    shell=False,
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
