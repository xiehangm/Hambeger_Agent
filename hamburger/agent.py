"""
hamburger.agent —— BurgerAgent 门面类

封装 graph + checkpointer + thread_id + 网关，对外暴露统一的 stream / invoke / resume。
所有外部消费者（server / combo / 测试）只通过本类与 Agent 对话。
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, Optional

from langgraph.graph.state import CompiledStateGraph

from hamburger.gateway import AgentCard, AgentEvent, AgentRequest
from hamburger.ingredients.bread import BottomBread, TopBread
from hamburger.recipes import Recipe


class BurgerAgent:
    """一个汉堡 = 一个独立 Agent 模块。

    生命周期：
      - 构建时一次性持有 graph / 网关 / thread_id；
      - 持有期内不再重编译；
      - 销毁等同于会话结束。
    """

    def __init__(
        self,
        *,
        graph: CompiledStateGraph,
        recipe: Recipe,
        top_bread: TopBread,
        bottom_bread: BottomBread,
        thread_id: str,
        card: Optional[AgentCard] = None,
    ) -> None:
        self._graph = graph
        self._recipe = recipe
        self._top = top_bread
        self._bottom = bottom_bread
        self._thread_id = thread_id

        caps = (recipe or {}).get("capabilities", {}) or {}
        self._uses_checkpointer = bool(caps.get("memory") or caps.get("hitl"))

        # 能力卡：不传则从 recipe 推导一个默认卡，保证 .card 总是可用
        self._card = card or AgentCard(
            node_id="agent",
            name=(recipe or {}).get("label", (recipe or {}).get("name", "agent")),
            description=(recipe or {}).get("description", ""),
            recipe_name=(recipe or {}).get("name", ""),
            capabilities=dict(caps),
            tool_names=[],
        )

    # ------------------------------------------------------------------ #
    # 属性
    # ------------------------------------------------------------------ #
    @property
    def thread_id(self) -> str:
        return self._thread_id

    @property
    def recipe(self) -> Recipe:
        return self._recipe

    @property
    def recipe_name(self) -> str:
        return (self._recipe or {}).get("name", "")

    @property
    def graph(self) -> CompiledStateGraph:
        """直接访问内部 graph —— 仅供调试，正常路径请走 stream/invoke/resume。"""
        return self._graph

    @property
    def top_bread(self) -> TopBread:
        return self._top

    @property
    def bottom_bread(self) -> BottomBread:
        return self._bottom

    @property
    def uses_checkpointer(self) -> bool:
        return self._uses_checkpointer

    @property
    def card(self) -> AgentCard:
        """能力卡：供 ComboGateway 注册与路由 LLM 阅读。"""
        return self._card

    # ------------------------------------------------------------------ #
    # 主入口：流式
    # ------------------------------------------------------------------ #
    async def stream(self, req: AgentRequest) -> AsyncIterator[AgentEvent]:
        """统一流式生成器。

        事件序列：node*, tool*, intent?, tool_plan?, token*, (interrupt | final), done
        """
        cfg = {"configurable": {"thread_id": self._thread_id}}
        inp = self._top.prepare_input(req)

        final_state: Dict[str, Any] = {}
        try:
            async for raw in self._graph.astream_events(inp, config=cfg, version="v2"):
                # 翻译事件
                for ev in self._bottom.handle_raw_event(raw):
                    yield ev
                    await asyncio.sleep(0)
                # 同步截获 final_state
                etype = raw.get("event", "")
                name = raw.get("name", "")
                if etype == "on_chain_end":
                    out = (raw.get("data") or {}).get("output")
                    if name == "bottom_bread" and isinstance(out, dict):
                        final_state = out
                    elif name == "LangGraph" and isinstance(out, dict):
                        final_state = out

            # 流结束后判断是否处于 HITL 暂停
            if self._uses_checkpointer:
                snap = self._graph.get_state(cfg)
                next_nodes = list(snap.next) if snap and snap.next else []
                if next_nodes:
                    pending = self._bottom.detect_interrupt(
                        snap.values if snap else {},
                        recipe=self._recipe,
                    )
                    yield AgentEvent.interrupt(next_nodes, pending or {})
                    yield AgentEvent.done()
                    return
                if snap is not None:
                    final_state = snap.values or final_state

            reply = self._bottom.extract_final(final_state)
            yield AgentEvent.final(reply, len((final_state or {}).get("messages") or []))
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            yield AgentEvent.error(str(exc))
        finally:
            yield AgentEvent.done()

    # ------------------------------------------------------------------ #
    # 主入口：非流式
    # ------------------------------------------------------------------ #
    async def invoke(self, req: AgentRequest) -> AgentEvent:
        """消费 stream，返回最后一个 final / interrupt / error 事件。"""
        last_meaningful: Optional[AgentEvent] = None
        async for ev in self.stream(req):
            if ev.kind in ("final", "interrupt", "error"):
                last_meaningful = ev
        return last_meaningful or AgentEvent.error("no events produced")

    # ------------------------------------------------------------------ #
    # HITL 续跑
    # ------------------------------------------------------------------ #
    async def resume(
        self,
        approved: bool,
        note: Optional[str] = None,
    ) -> AsyncIterator[AgentEvent]:
        """HITL 审批后续跑。

        - approved=True  : 清空 pending_approval，让 graph 继续往下走（执行工具）。
        - approved=False : 写入 rejected 标记，让 graph 走拒绝分支或终止。
        """
        cfg = {"configurable": {"thread_id": self._thread_id}}
        update: Dict[str, Any] = {"pending_approval": None} if approved else {
            "pending_approval": {"rejected": True, "note": note},
        }
        try:
            self._graph.update_state(cfg, update)
        except Exception as exc:  # noqa: BLE001
            yield AgentEvent.error(f"resume update_state failed: {exc}")
            yield AgentEvent.done()
            return

        async for ev in self.stream(
            AgentRequest(message=None, resume=True,
                         approval={"approved": approved, "note": note}),
        ):
            yield ev

    # ------------------------------------------------------------------ #
    # 状态快照（给 server / combo / UI 查询）
    # ------------------------------------------------------------------ #
    def snapshot(self) -> Dict[str, Any]:
        cfg = {"configurable": {"thread_id": self._thread_id}}
        try:
            snap = self._graph.get_state(cfg) if self._uses_checkpointer else None
        except Exception:
            snap = None
        values = (snap.values if snap else {}) or {}
        return {
            "thread_id": self._thread_id,
            "recipe_name": self.recipe_name,
            "next": list(snap.next) if snap and snap.next else [],
            "values": values,
        }
