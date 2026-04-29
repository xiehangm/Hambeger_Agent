"""
顶部面包 / 底部面包 —— 既是图内节点，也是 Agent 的入站 / 出站网关。

双重身份：
  - process(state)         : LangGraph 节点行为（入图运行）
  - prepare_input(req)     : 入站网关方法（外界 → 图）
  - handle_raw_event(ev)   : 出站网关方法（图内事件 → AgentEvent）
  - extract_final(state)   : 出站网关方法（最终回复抽取）
  - detect_interrupt(state): 出站网关方法（HITL 暂停检测）
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from langchain_core.messages import AIMessage, HumanMessage

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient
from hamburger.gateway import (
    AgentEvent,
    AgentRequest,
    InboundGateway,
    OutboundGateway,
)


# ============================================================
#  顶部面包 —— 入站网关
# ============================================================
class TopBread(HamburgerIngredient, InboundGateway):
    """顶层面包：图内输入预处理节点 + 入站网关。"""

    # ---- 图节点行为 ----
    def process(self, state: HamburgerState) -> Dict[str, Any]:
        input_text = state.get("input_text", "")
        return {"messages": [HumanMessage(content=input_text)]}

    # ---- 入站网关 ----
    def prepare_input(self, req: AgentRequest) -> Optional[Dict[str, Any]]:
        """把 AgentRequest 翻译为图的初始输入 state。

        - resume 场景返回 None（由 BurgerAgent 把 None 喂给 astream_events，
          让 LangGraph 从 checkpointer 恢复执行，不注入新一轮 input）。
        - 普通对话返回 ``{"input_text": ..., "messages": []}``。
        """
        if req.resume:
            return None
        initial: Dict[str, Any] = {
            "input_text": req.message or "",
            "messages": [],
        }
        if req.parent_ctx:
            initial["context"] = dict(req.parent_ctx)
        return initial


# ============================================================
#  底部面包 —— 出站网关
# ============================================================
class BottomBread(HamburgerIngredient, OutboundGateway):
    """底层面包：图内输出整理节点 + 出站网关。

    所有"把 graph 内部信号翻译给外界"的逻辑都收口在这里：
    节点事件序列化、工具调用计划抽取、意图标签映射、HITL 暂停检测、终态回复抽取。
    """

    #: 关心的图节点白名单 —— 子类可覆盖以适配自定义 recipe
    INTERESTING_NODES: set = {
        "top_bread", "cheese", "onion", "meat",
        "vegetable", "pickle", "bottom_bread",
    }

    #: 意图 ID → 中文标签，未命中则原样返回
    INTENT_LABELS: Dict[str, str] = {
        "chat": "闲聊 / 直接回答",
        "search": "搜索 / 查找信息",
        "compute": "计算 / 求值",
    }

    #: HITL 默认审批提示，可被 recipe 中 pickle 节点 params.hint 覆盖
    DEFAULT_APPROVAL_HINT = "是否允许执行上述工具调用？"

    # ---------------- 图节点行为 ----------------
    def process(self, state: HamburgerState) -> Dict[str, Any]:
        messages = state.get("messages", [])
        content = messages[-1].content if messages else ""
        return {"output_text": content}

    # ---------------- 出站网关 ----------------
    def handle_raw_event(self, ev: Dict[str, Any]) -> Iterable[AgentEvent]:
        """把 graph.astream_events v2 的单个原始事件翻译为 AgentEvent 序列。"""
        etype = ev.get("event", "")
        name = ev.get("name", "")
        data = ev.get("data") or {}

        if etype == "on_chain_start" and name in self.INTERESTING_NODES:
            yield AgentEvent.node(name, "start")
            return

        if etype == "on_chain_end" and name in self.INTERESTING_NODES:
            output = data.get("output")
            # onion → 意图分类副事件
            if name == "onion":
                intent_id = self._extract_intent(output)
                if intent_id and intent_id != "_pending":
                    yield AgentEvent.intent(intent_id, self._intent_label(intent_id))
                # PR-B：onion 如果写了 handoff_target，额外发 handoff 事件
                target = self._extract_handoff_target(output)
                if target:
                    yield AgentEvent.handoff(target=target, reason=intent_id or "")
                # I-2：onion mode=ask_router 时让总网关接管路由
                ask = self._extract_ask_router(output)
                if ask:
                    yield AgentEvent.ask_router(
                        hint=ask.get("hint", "") or "",
                        candidates=ask.get("candidates") or [],
                    )
            # meat → 工具调用计划副事件
            elif name == "meat":
                ai = self._extract_last_ai_message(output)
                if ai is not None and getattr(ai, "tool_calls", None):
                    yield AgentEvent.tool_plan(
                        self._serialize_tool_calls(ai.tool_calls),
                        (ai.content or "")[:160],
                    )
            # I-3：vegetable end 时抽出远程委托，逐条发 delegate 事件
            elif name == "vegetable":
                pendings = self._extract_pending_delegations(output)
                for p in pendings:
                    args = p.get("args") or {}
                    msg = self._format_delegate_message(p.get("name"), args)
                    yield AgentEvent.delegate(
                        target=p.get("target") or "",
                        message=msg,
                        carry={
                            "tool_call_id": p.get("tool_call_id"),
                            "name": p.get("name"),
                            "args": args,
                        },
                    )
            yield AgentEvent.node(name, "end")
            return

        if etype == "on_tool_start":
            yield AgentEvent.tool_start(name, data.get("input"))
            return

        if etype == "on_tool_end":
            yield AgentEvent.tool_end(name, self._format_tool_output(data.get("output")))
            return

        if etype == "on_chat_model_stream":
            text = self._extract_token_text(data.get("chunk"))
            if text:
                yield AgentEvent.token(text)
            return

    def extract_final(self, state: Dict[str, Any]) -> str:
        if not isinstance(state, dict):
            return ""
        if state.get("output_text"):
            return str(state["output_text"])
        messages = state.get("messages") or []
        for m in reversed(messages):
            content = getattr(m, "content", None)
            if isinstance(content, str) and content.strip() and getattr(m, "type", "") != "tool":
                return content
        return ""

    def detect_interrupt(
        self,
        state: Dict[str, Any],
        *,
        recipe: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """从 state 抽取 HITL 待审批载荷。

        约定：
          - state 中已有 ``pending_approval.tool_calls`` → 直接返回。
          - 否则现场解析 messages 最后一条 AIMessage 的 tool_calls 合成。
          - hint 来自 recipe 的 pickle 节点 params.hint，缺省走类常量。
        """
        if not isinstance(state, dict):
            return None
        existing = state.get("pending_approval") or {}
        if isinstance(existing, dict) and existing.get("tool_calls"):
            return existing

        messages = state.get("messages") or []
        last = messages[-1] if messages else None
        pending_tools: List[Dict[str, Any]] = []
        if isinstance(last, AIMessage):
            pending_tools = self._serialize_tool_calls(getattr(last, "tool_calls", []) or [])

        if not pending_tools:
            return None

        hint = self.DEFAULT_APPROVAL_HINT
        for node in (recipe or {}).get("nodes", []) or []:
            if node.get("type") == "pickle":
                hint = (node.get("params") or {}).get("hint", hint)
                break

        return {"hint": hint, "tool_calls": pending_tools}

    # ---------------- 内部辅助 ----------------
    @staticmethod
    def _serialize_tool_calls(tool_calls: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for tc in tool_calls or []:
            out.append({
                "name": tc.get("name"),
                "args": tc.get("args") or {},
                "id": tc.get("id"),
            })
        return out

    @staticmethod
    def _extract_last_ai_message(output: Any) -> Optional[AIMessage]:
        if isinstance(output, AIMessage):
            return output
        if isinstance(output, dict):
            for msg in reversed(output.get("messages") or []):
                if isinstance(msg, AIMessage):
                    return msg
        return None

    @staticmethod
    def _extract_intent(output: Any) -> Optional[str]:
        if isinstance(output, dict):
            intent = output.get("intent")
            if intent:
                return str(intent)
        return None

    @staticmethod
    def _extract_handoff_target(output: Any) -> Optional[str]:
        """PR-B：从 onion 节点输出中提取 handoff_target（不存在返回 None）。"""
        if isinstance(output, dict):
            target = output.get("handoff_target")
            if target:
                return str(target)
        return None

    @staticmethod
    def _extract_ask_router(output: Any) -> Optional[Dict[str, Any]]:
        """I-2：从 onion 节点输出中提取 ask_router_request（不存在返回 None）。"""
        if isinstance(output, dict):
            req = output.get("ask_router_request")
            if isinstance(req, dict):
                return req
        return None

    @staticmethod
    def _extract_pending_delegations(output: Any) -> List[Dict[str, Any]]:
        """I-3：从 vegetable 节点输出中提取远程委托列表。"""
        if isinstance(output, dict):
            items = output.get("pending_delegations")
            if isinstance(items, list):
                return [p for p in items if isinstance(p, dict)]
        return []

    @staticmethod
    def _format_delegate_message(name: Optional[str], args: Dict[str, Any]) -> str:
        if not args:
            return f"调用工具 {name or ''}"
        try:
            import json as _json
            return _json.dumps({"tool": name, "args": args}, ensure_ascii=False)
        except Exception:
            return f"调用工具 {name or ''}：{args}"

    def _intent_label(self, intent_id: Optional[str]) -> str:
        return self.INTENT_LABELS.get(intent_id or "", intent_id or "未知")

    @staticmethod
    def _format_tool_output(out: Any) -> Optional[str]:
        if out is None:
            return None
        try:
            if hasattr(out, "content"):
                text = getattr(out, "content", None)
            elif isinstance(out, dict) and out.get("content"):
                text = out.get("content")
            else:
                text = str(out)
            if text is None:
                return None
            text = str(text)
            return text[:400] + "..." if len(text) > 400 else text
        except Exception:
            return None

    @staticmethod
    def _extract_token_text(chunk: Any) -> Optional[str]:
        if chunk is None:
            return None
        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            return content or None
        if isinstance(content, list):
            parts = [
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return "".join(parts) or None
        return None
