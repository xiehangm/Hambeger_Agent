"""
hamburger.gateway.contracts —— 网关协议定义

设计要点：
1. AgentEvent 的 kind 与 payload 字段，序列化后 SSE JSON 必须与现有 server `_sse({...})`
   的键名/取值完全一致（前端零改动）。
2. 网关基类用 typing.Protocol（结构化子类型），实现方无需显式继承，
   但 TopBread / BottomBread 会显式继承以获得 IDE 类型提示。
3. 本模块零外部依赖（除标准库 + langchain_core），保证可以脱离 server / fastapi 测试。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional, Protocol, runtime_checkable


# ============================================================
#  事件类型
# ============================================================
EventKind = Literal[
    "node",        # 节点 start / end
    "tool",        # 工具 start / end
    "tool_plan",   # 肉饼推理出来的 tool_calls 计划
    "intent",      # 洋葱意图分类
    "token",       # LLM token 流
    "interrupt",   # HITL 暂停
    "final",       # 最终回复
    "error",       # 异常
    "done",        # 流终止哨兵
    # ↓↓↓ PR-B 新增：套餐内部事件，默认不外送给前端
    "handoff",     # Agent 主动转交：next_agent
    "delegate",    # Agent 同步委托：调用别的 Agent 拿一段输出
    "ask_router",  # Agent 让总网关帮忙挑下一步
]


# ============================================================
#  入站请求
# ============================================================
# ============================================================
#  能力卡（PR-A 新增）
# ============================================================
@dataclass(frozen=True)
class AgentCard:
    """单个 BurgerAgent 的能力描述，套餐场景下由 ComboGateway 收集为注册表 +
    路由 LLM 提示。单 Agent 直接跑时 node_id 默认 ``"agent"``。

    字段语义：
      - node_id      : 套餐内全局唯一的节点名
      - name         : 人类可读名称
      - description  : 1~2 句用途（喜给路由 LLM 阅读）
      - recipe_name  : 被编译的 recipe.name
      - capabilities : 复用 recipe.capabilities
      - tool_names   : 该 Agent 能调用的工具名列表
      - tags         : 可选标签，供路由过滤使用
    """
    node_id: str
    name: str
    description: str
    recipe_name: str
    capabilities: Dict[str, bool] = field(default_factory=dict)
    tool_names: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_markdown_line(self) -> str:
        """输出一行 markdown，供路由 LLM 阅读：``- `node_id` (name) — description``"""
        return f"- `{self.node_id}` ({self.name}) — {self.description}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentRequest:
    """外界 → Agent 的统一请求。

    字段语义：
      - message:     用户输入；resume 场景下可为 None
      - resume:      是否为 HITL 审批后的续跑
      - approval:    审批结果，{"approved": bool, "note": Optional[str]}
      - parent_ctx:  Combo 父图传入的上下文（可选）
    """
    message: Optional[str] = None
    resume: bool = False
    approval: Optional[Dict[str, Any]] = None
    parent_ctx: Optional[Dict[str, Any]] = None


# ============================================================
#  出站事件
# ============================================================
@dataclass
class AgentEvent:
    """Agent → 外界 的统一事件。

    序列化协议：to_sse() 输出 ``data: {"type": <kind>, **payload}\\n\\n``。
    payload 内的键名必须与前端约定一致：
      - node : {"name": str, "status": "start"|"end"}
      - tool : {"name": str, "status": "start"|"end", "input"?: Any, "output"?: Any}
      - tool_plan : {"tool_calls": list[dict], "summary": str}
      - intent : {"intent": str, "label": str}
      - token : {"text": str}
      - interrupt : {"next": list[str], "pending": dict}
      - final : {"reply": str, "messages": int}
      - error : {"detail": str}
      - done : {}
    """
    kind: EventKind
    payload: Dict[str, Any] = field(default_factory=dict)

    # ---- 序列化 ----
    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.kind, **self.payload}

    def to_sse(self) -> bytes:
        return f"data: {json.dumps(self.to_dict(), ensure_ascii=False)}\n\n".encode("utf-8")

    # ---- 工厂便捷方法 ----
    @classmethod
    def node(cls, name: str, status: Literal["start", "end"]) -> "AgentEvent":
        return cls("node", {"name": name, "status": status})

    @classmethod
    def tool_start(cls, name: str, tool_input: Any = None) -> "AgentEvent":
        return cls("tool", {"name": name, "status": "start", "input": tool_input})

    @classmethod
    def tool_end(cls, name: str, tool_output: Any = None) -> "AgentEvent":
        return cls("tool", {"name": name, "status": "end", "output": tool_output})

    @classmethod
    def tool_plan(cls, tool_calls: list, summary: str = "") -> "AgentEvent":
        return cls("tool_plan", {"tool_calls": list(tool_calls), "summary": summary})

    @classmethod
    def intent(cls, intent_id: str, label: str) -> "AgentEvent":
        return cls("intent", {"intent": intent_id, "label": label})

    @classmethod
    def token(cls, text: str) -> "AgentEvent":
        return cls("token", {"text": text})

    @classmethod
    def interrupt(cls, next_nodes: list, pending: Dict[str, Any]) -> "AgentEvent":
        return cls("interrupt", {"next": list(next_nodes), "pending": pending})

    @classmethod
    def final(cls, reply: str, messages: int) -> "AgentEvent":
        return cls("final", {"reply": reply, "messages": messages})

    @classmethod
    def error(cls, detail: str) -> "AgentEvent":
        return cls("error", {"detail": detail})

    @classmethod
    def done(cls) -> "AgentEvent":
        return cls("done", {})

    # ---- PR-B 新增：套餐内部路由事件 ----
    @classmethod
    def handoff(cls, *, target: str, reason: str = "", carry: Any = None) -> "AgentEvent":
        """Agent 主动转交给同套餐内另一个 Agent。"""
        return cls("handoff", {"target": target, "reason": reason, "carry": carry})

    @classmethod
    def delegate(cls, *, target: str, message: str, carry: Any = None) -> "AgentEvent":
        """Agent 同步委托另一个 Agent 拿一段输出。"""
        return cls("delegate", {"target": target, "message": message, "carry": carry})

    @classmethod
    def ask_router(cls, *, hint: str, candidates: Optional[List[str]] = None) -> "AgentEvent":
        """请求总网关路由 LLM 选下一个 Agent。"""
        return cls("ask_router", {"hint": hint, "candidates": list(candidates or [])})


# ============================================================
#  网关接口（结构化协议）
# ============================================================
@runtime_checkable
class InboundGateway(Protocol):
    """入站网关：把 AgentRequest 翻译为图的初始 state。

    返回 None 表示 resume 场景（不向 graph 注入新输入）。
    """

    def prepare_input(self, req: AgentRequest) -> Optional[Dict[str, Any]]:
        ...


@runtime_checkable
class OutboundGateway(Protocol):
    """出站网关：把 graph 内部事件 / 状态翻译为对外的 AgentEvent。"""

    def handle_raw_event(self, ev: Dict[str, Any]) -> Iterable[AgentEvent]:
        """把 graph.astream_events(version='v2') 的单个原始事件翻译为 0..N 个 AgentEvent。"""
        ...

    def extract_final(self, state: Dict[str, Any]) -> str:
        """从最终 state 中抽取可展示的回复文本。"""
        ...

    def detect_interrupt(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """检查 state 是否处于 HITL 待审批态；返回 pending payload 或 None。"""
        ...
