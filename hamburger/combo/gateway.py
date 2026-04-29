"""
hamburger/combo/gateway.py — 套餐级网关 / 总线 / 调度中枢

职责：
  1. 注册子 BurgerAgent（node_id → agent）
  2. 收集 AgentCard，对路由 LLM 暴露 describe()
  3. 提供 adapt(node_id) 把 Agent 适配为 LangGraph 节点函数
  4. 拦截子 Agent 的 handoff/delegate/ask_router 事件并改写 ComboState

本步（PR-C）只把老 _wrap_burger_as_node 的能力收进来，行为与旧实现等价；
PR-D 起会基于 ComboGateway 实现动态路由 / Supervisor / 真 handoff 边。
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_core.messages import AIMessage, ToolMessage

from hamburger.agent import BurgerAgent
from hamburger.gateway import AgentCard, AgentEvent, AgentRequest


class ComboGateway:
    """套餐内部的多 Agent 总线。"""

    def __init__(
        self,
        *,
        max_handoffs: int = 8,
        router_llm_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._agents: Dict[str, BurgerAgent] = {}
        self._cards: Dict[str, AgentCard] = {}
        self._max_handoffs = max_handoffs
        # I-2：供 ask_router 事件使用的路由 LLM。
        # 以 factory 形式传入，区分与 burger 的 meat_patty LLM，便于用便宜 mini。
        self._router_llm_factory = router_llm_factory
        # PR-G: 子 Agent 事件冒泡总线（由 server 在每次 SSE 请求时挂入）
        self._bus: Optional[asyncio.Queue] = None

    # —— 事件总线（PR-G）——
    def attach_bus(self, bus: "asyncio.Queue") -> None:
        self._bus = bus

    def detach_bus(self) -> None:
        self._bus = None

    async def _emit(self, node_id: str, ev: AgentEvent) -> None:
        if self._bus is None:
            return
        wrapped = AgentEvent(
            kind="combo_burger_event",
            payload={"combo_node_id": node_id, "inner": ev.to_dict()},
        )
        try:
            self._bus.put_nowait(wrapped)
        except asyncio.QueueFull:
            # 满了优先丢 token
            if ev.kind != "token":
                await self._bus.put(wrapped)

    # —— 注册 ——
    def register(self, agent: BurgerAgent) -> None:
        node_id = agent.card.node_id
        if node_id in self._agents:
            raise ValueError(f"node_id 冲突: {node_id}")
        self._agents[node_id] = agent
        self._cards[node_id] = agent.card

    def unregister(self, node_id: str) -> None:
        self._agents.pop(node_id, None)
        self._cards.pop(node_id, None)

    def has(self, node_id: str) -> bool:
        return node_id in self._agents

    def get(self, node_id: str) -> Optional[BurgerAgent]:
        return self._agents.get(node_id)

    def cards(self) -> List[AgentCard]:
        return list(self._cards.values())

    def describe(self, *, only: Optional[List[str]] = None) -> str:
        """生成喂给路由 LLM 的 markdown 列表。"""
        keys = only if only is not None else list(self._cards.keys())
        return "\n".join(self._cards[k].to_markdown_line() for k in keys if k in self._cards)

    @property
    def max_handoffs(self) -> int:
        return self._max_handoffs

    # —— 调度（同步一次）——
    async def run_agent(
        self,
        node_id: str,
        *,
        message: str,
        parent_ctx: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """调用一个 Agent 跑一轮。

        返回结构：
          {
            "reply": str,                     # final 事件抽到的回复（可能为空）
            "handoff": Optional[dict],        # 第一个 handoff 事件 payload
            "kind": str,                      # 最后一个有意义事件的 kind
            "payload": dict,                  # 对应 payload
            "thread_id": str,
          }
        """
        agent = self._agents.get(node_id)
        if agent is None:
            return {
                "reply": "",
                "handoff": None,
                "kind": "error",
                "payload": {"detail": f"未知 node_id: {node_id}"},
                "thread_id": "",
            }

        req = AgentRequest(message=message, parent_ctx=parent_ctx or {})
        reply = ""
        handoff: Optional[Dict[str, Any]] = None
        ask_router_payload: Optional[Dict[str, Any]] = None
        delegate_events: List[Dict[str, Any]] = []
        last_kind = ""
        last_payload: Dict[str, Any] = {}

        async for ev in agent.stream(req):
            await self._emit(node_id, ev)
            if ev.kind == "handoff" and handoff is None:
                handoff = dict(ev.payload)
            elif ev.kind == "ask_router" and ask_router_payload is None:
                ask_router_payload = dict(ev.payload)
            elif ev.kind == "delegate":
                delegate_events.append(dict(ev.payload))
            elif ev.kind == "final":
                reply = ev.payload.get("reply", "") or ""
                last_kind = "final"
                last_payload = dict(ev.payload)
            elif ev.kind == "interrupt":
                last_kind = "interrupt"
                last_payload = dict(ev.payload)
            elif ev.kind == "error":
                last_kind = "error"
                last_payload = dict(ev.payload)

        # I-2：如果子 Agent 发了 ask_router 且还没有 handoff，调路由 LLM 帮它选下一个。
        if handoff is None and ask_router_payload is not None:
            try:
                picked = await self._route_with_llm(
                    hint=ask_router_payload.get("hint", "") or message,
                    candidates=ask_router_payload.get("candidates") or [],
                )
            except Exception as exc:  # router 不可用不能阻断套餐
                picked = None
                last_kind = last_kind or "error"
                last_payload = last_payload or {
                    "detail": f"router_llm 失败: {exc}"}
            if picked:
                handoff = {
                    "target": picked,
                    "reason": "ask_router",
                    "carry": ask_router_payload.get("hint"),
                }

        return {
            "reply": reply,
            "handoff": handoff,
            "kind": last_kind,
            "payload": last_payload,
            "thread_id": agent.thread_id,
            "delegations": await self._dispatch_delegations(
                node_id, delegate_events, parent_ctx=parent_ctx
            ),
        }

    # I-3：逐条调用远程 Agent 帮原 Agent 完成被委托的工具调用
    async def _dispatch_delegations(
        self,
        from_node: str,
        events: List[Dict[str, Any]],
        *,
        parent_ctx: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not events:
            return results
        for p in events:
            target = p.get("target") or ""
            carry = dict(p.get("carry") or {})
            tool_call_id = carry.get("tool_call_id") or ""
            name = carry.get("name") or ""
            if not target or not self.has(target):
                results.append({
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "target": target,
                    "content": f"[delegate 失败：未知目标 {target!r}]",
                    "ok": False,
                })
                continue
            sub = await self.run_agent(
                target,
                message=p.get("message") or "",
                parent_ctx={
                    **(parent_ctx or {}),
                    "delegated_from": from_node,
                    "delegated_tool": name,
                },
            )
            results.append({
                "tool_call_id": tool_call_id,
                "name": name,
                "target": target,
                "content": sub.get("reply") or "",
                "ok": True,
            })
        return results

    # I-2：调 router LLM 在候选集里选一个 Agent 节点
    async def _route_with_llm(
        self,
        *,
        hint: str,
        candidates: List[str],
    ) -> Optional[str]:
        if not candidates:
            candidates = list(self._cards.keys())
        # 只允许选已注册的节点
        candidates = [c for c in candidates if c in self._cards] or candidates
        if not candidates:
            return None
        if self._router_llm_factory is None:
            return candidates[0]
        desc = self.describe(only=candidates) or "\n".join(
            f"- {c}" for c in candidates)
        prompt = (
            "你是 Agent 路由器，请从以下候选中选一个最适合处理输入的 node_id，"
            "只输出 node_id 字符串本身，不要其他解释。\n"
            f"候选：\n{desc}\n\n输入：{hint}"
        )
        llm = self._router_llm_factory()
        invoke = getattr(llm, "ainvoke", None)
        resp = await invoke(prompt) if invoke else llm.invoke(prompt)
        raw = getattr(resp, "content", None) or str(resp)
        raw = (raw or "").strip()
        for c in candidates:
            if raw == c:
                return c
        for c in sorted(candidates, key=len, reverse=True):
            if c in raw:
                return c
        return candidates[0]

    # —— 适配为 LangGraph 节点 ——
    def adapt(
        self,
        node_id: str,
        *,
        input_field: str = "user_input",
        input_template: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
        """返回一个 LangGraph 节点函数。

        参数：
          input_field   : 默认从 ComboState 哪个字段取输入文本（默认 user_input）
          input_template: 若提供，则用 ``str.format_map(state)`` 渲染输入
          extra_meta    : 额外要写进 burger_meta[node_id] 的常量元数据（如 burger_id）
        """
        meta_const: Dict[str, Any] = dict(extra_meta or {})

        async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
            if input_template:
                try:
                    text = input_template.format_map(
                        {k: (v if v is not None else "")
                         for k, v in state.items()}
                    )
                except Exception:
                    text = str(state.get(input_field) or "")
            else:
                text = str(state.get(input_field) or "")

            result = await self.run_agent(
                node_id,
                message=text,
                parent_ctx={
                    "combo_node_id": node_id,
                    "user_input": state.get("user_input", ""),
                    **{k: v for k, v in meta_const.items() if k != "agent_type"},
                },
            )

            reply = result["reply"]
            messages_out: List[Any] = [
                AIMessage(content=reply or "", name=node_id)]
            # I-3：委托的远程工具调用结果 → ToolMessage 写回 combo messages
            for d in result.get("delegations") or []:
                if not d.get("tool_call_id"):
                    continue
                messages_out.append(ToolMessage(
                    content=str(d.get("content") or ""),
                    tool_call_id=d["tool_call_id"],
                    name=d.get("name") or "",
                ))
            update: Dict[str, Any] = {
                "burger_outputs": {node_id: reply},
                "burger_meta": {
                    node_id: {
                        **meta_const,
                        "thread_id": result["thread_id"],
                        "final_kind": result["kind"],
                    }
                },
                "combo_trace": [{
                    "kind": "burger",
                    "node_id": node_id,
                    **({"burger_id": meta_const["burger_id"]} if "burger_id" in meta_const else {}),
                    "output": (reply or "")[:500],
                }],
                "messages": messages_out,
                "active_agent": node_id,
                "visited_agents": [node_id],
            }
            for d in result.get("delegations") or []:
                update["combo_trace"].append({
                    "kind": "delegate",
                    "from": node_id,
                    "target": d.get("target"),
                    "tool": d.get("name"),
                    "ok": d.get("ok"),
                })
            ho = result.get("handoff")
            if ho:
                update["handoff_request"] = ho
                update["combo_trace"].append({
                    "kind": "handoff",
                    "from": node_id,
                    "target": ho.get("target"),
                    "reason": ho.get("reason"),
                })
            return update

        _node.__name__ = f"agent_{node_id}"
        return _node
