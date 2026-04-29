"""
hamburger.tools.remote — 远程委托工具

I-3：声明一个"看起来像本地工具、但实际由 ComboGateway 路由到指定 Agent 完成"
的 ``BaseTool`` 子类。LLM 的 ``bind_tools`` 只需要 name / description / args_schema，
所以本类只暴露这些字段；``_run`` / ``_arun`` 直接抛错 —— ``Vegetable`` 节点会先
把这种工具调用拆出去，永远不会真的让 ``ToolNode`` 调到。
"""
from __future__ import annotations

from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel


class RemoteTool(BaseTool):
    """委托给套餐内另一个 Agent 完成的虚拟工具。

    属性：
      - delegate_to: ComboGateway 中的 node_id
    """

    # BaseTool 已声明 name / description；下面的字段是新增。
    delegate_to: str = ""

    def _run(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - 不应被调用
        raise RuntimeError(
            f"RemoteTool {self.name!r} 不可本地执行，"
            f"应由 Vegetable 节点拆解为 delegate 事件转发到 {self.delegate_to!r}。"
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        return self._run(*args, **kwargs)


def build_remote_tool(
    *,
    name: str,
    description: str,
    delegate_to: str,
    args_schema: Optional[Type[BaseModel]] = None,
) -> RemoteTool:
    """构造 RemoteTool 实例。

    :param name: 给 LLM 看的工具名。
    :param description: 工具描述（喂给 LLM）。
    :param delegate_to: ComboGateway 中的目标 node_id。
    :param args_schema: pydantic ``BaseModel`` 类，用于结构化参数；可缺省。
    """
    kwargs: dict = {
        "name": name,
        "description": description,
        "delegate_to": delegate_to,
    }
    if args_schema is not None:
        kwargs["args_schema"] = args_schema
    return RemoteTool(**kwargs)
