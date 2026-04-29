"""
🥬 Vegetable —— 工具执行节点。

I-3：支持本地工具 (BaseTool) 与远程工具 (RemoteTool) 混搭。
  - 本地调用走 LangGraph 内置 ToolNode，表现完全与旧版一致。
  - 远程调用不本地执行，写入 ``state.pending_delegations`` 并补一条占位
    ToolMessage(内容为 ``[delegating to <target>]``)，让 MeatPatty 本轮循环能
    接上去。BottomBread 会在 vegetable end 时发出 ``AgentEvent.delegate``，
    总网关 ComboGateway 在该轮 Agent 跑完后一起跟进。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient
from hamburger.tools.remote import RemoteTool


class Vegetable(HamburgerIngredient):
    """工具执行节点；混搭 local + remote 工具。"""

    def __init__(self, tools: List[BaseTool]):
        self.tools = list(tools or [])
        self.local_tools: List[BaseTool] = []
        self.remote_specs: Dict[str, RemoteTool] = {}
        for t in self.tools:
            if isinstance(t, RemoteTool) or getattr(t, "delegate_to", None):
                self.remote_specs[t.name] = t  # type: ignore[index]
            else:
                self.local_tools.append(t)
        self.tool_node: Optional[ToolNode] = (
            ToolNode(self.local_tools) if self.local_tools else None
        )

    def process(self, state: HamburgerState) -> Dict[str, Any]:
        msgs = list(state.get("messages") or [])
        if not msgs or not isinstance(msgs[-1], AIMessage):
            return {}
        ai = msgs[-1]
        tool_calls = list(getattr(ai, "tool_calls", []) or [])
        if not tool_calls:
            return {}

        local_calls = [tc for tc in tool_calls if tc.get("name") not in self.remote_specs]
        remote_calls = [tc for tc in tool_calls if tc.get("name") in self.remote_specs]

        out: Dict[str, Any] = {}

        # --- 本地工具：交给 ToolNode，但只传本地那部分 tool_calls ---
        if local_calls and self.tool_node is not None:
            if len(local_calls) == len(tool_calls):
                local_state = state
            else:
                local_ai = AIMessage(
                    content=ai.content,
                    tool_calls=local_calls,
                    additional_kwargs=copy.copy(getattr(ai, "additional_kwargs", {}) or {}),
                    response_metadata=copy.copy(getattr(ai, "response_metadata", {}) or {}),
                    id=getattr(ai, "id", None),
                )
                local_state = {**state, "messages": msgs[:-1] + [local_ai]}
            local_out = self.tool_node.invoke(local_state)
            local_msgs = list((local_out or {}).get("messages") or [])
            if local_msgs:
                out["messages"] = local_msgs

        # --- 远程工具：占位 ToolMessage + pending_delegations ---
        if remote_calls:
            placeholders: List[ToolMessage] = []
            pending: List[Dict[str, Any]] = []
            for tc in remote_calls:
                spec = self.remote_specs[tc["name"]]
                target = getattr(spec, "delegate_to", "") or ""
                pending.append({
                    "target": target,
                    "tool_call_id": tc.get("id"),
                    "name": tc.get("name"),
                    "args": tc.get("args") or {},
                })
                placeholders.append(ToolMessage(
                    content=f"[delegating to {target}]",
                    tool_call_id=tc.get("id") or "",
                    name=tc.get("name"),
                ))
            existing = list(out.get("messages") or [])
            existing.extend(placeholders)
            out["messages"] = existing
            out["pending_delegations"] = pending

        return out

