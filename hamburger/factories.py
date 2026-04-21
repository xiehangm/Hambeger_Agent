"""
hamburger/factories.py — 节点工厂与条件路由注册表

把 Recipe 的声明式节点规格（NodeSpec）转化为具体的 LangGraph 节点 Runnable。
每个工厂读取 build_ctx（运行时构建上下文：llm、tools、cheese_prompt 等）
与 NodeSpec.params（来自配方蓝图的静态参数），返回一个可被 add_node 使用的对象。

当前支持的节点类型：
  - top_bread / bottom_bread / cheese / meat_patty / vegetable
  - interrupt_gate  : 占位节点（pass-through），配合 interrupt_before 使用
"""

from typing import Any, Callable, Dict, List, Literal, Optional
from langchain_core.messages import AIMessage

from hamburger.state import HamburgerState
from hamburger.ingredients.bread import TopBread, BottomBread
from hamburger.ingredients.cheese import Cheese
from hamburger.ingredients.meat import MeatPatty
from hamburger.ingredients.vegetable import Vegetable


# ============================================================
#  BuildContext 的 key 规范（仅作为约定，不强制）
# ============================================================
#   llm            : 已配置好的 ChatModel 实例（必需当配方含 meat_patty）
#   tools          : List[BaseTool]（可选；vegetable / meat_patty 会用）
#   cheese_prompt  : str（可选；cheese 节点会用）
#   recipe_name    : str（内部注入，用于状态标记）


# ============================================================
#  节点工厂
# ============================================================
NodeFactory = Callable[[Dict[str, Any], Dict[str, Any]], Any]


def _factory_top_bread(spec, ctx):
    return TopBread()


def _factory_bottom_bread(spec, ctx):
    return BottomBread()


def _factory_cheese(spec, ctx):
    params = spec.get("params", {}) or {}
    # 优先使用运行时 cheese_prompt，其次使用蓝图默认值
    prompt = ctx.get("cheese_prompt") or params.get(
        "default_prompt", "你是一个有用的智能助手")
    return Cheese(prompt)


def _factory_meat_patty(spec, ctx):
    llm = ctx.get("llm")
    if llm is None:
        raise ValueError("meat_patty 节点需要在 build_ctx 中提供 llm")
    tools = ctx.get("tools", []) or []
    return MeatPatty(llm=llm, tools=tools)


def _factory_vegetable(spec, ctx):
    tools = ctx.get("tools", []) or []
    if not tools:
        # 没有工具就没必要挂 vegetable 节点，返回 None 让编译器跳过
        return None
    return Vegetable(tools=tools)


def _factory_interrupt_gate(spec, ctx):
    """
    占位节点：本身不做任何处理。
    真正的暂停由 graph.compile(interrupt_before=[node_id]) 触发。
    节点运行时只是把 spec 中的 payload 写到 state.pending_approval，
    供前端判定是否处于审批状态。
    """
    params = spec.get("params", {}) or {}
    hint = params.get("hint", "请审核下一步操作")

    def _gate(state: HamburgerState) -> dict:
        messages = state.get("messages", []) or []
        last = messages[-1] if messages else None
        pending_tools: List[dict] = []
        if isinstance(last, AIMessage):
            for tc in getattr(last, "tool_calls", []) or []:
                pending_tools.append({
                    "name": tc.get("name"),
                    "args": tc.get("args"),
                    "id": tc.get("id"),
                })
        return {
            "pending_approval": {
                "hint": hint,
                "tool_calls": pending_tools,
            }
        }

    return _gate


NODE_FACTORIES: Dict[str, NodeFactory] = {
    "top_bread": _factory_top_bread,
    "bottom_bread": _factory_bottom_bread,
    "cheese": _factory_cheese,
    "meat_patty": _factory_meat_patty,
    "vegetable": _factory_vegetable,
    "interrupt_gate": _factory_interrupt_gate,
}


def register_factory(name: str, factory: NodeFactory) -> None:
    """对外暴露：允许第三方配方注册新的节点类型。"""
    NODE_FACTORIES[name] = factory


# ============================================================
#  条件路由
# ============================================================
def tools_condition(state: HamburgerState) -> Literal["tools", "end"]:
    """
    判断 LLM 最后一条消息是否要求调用工具。
    返回值与 Recipe.edges[].branches 的 key 对应。
    """
    messages = state.get("messages", []) or []
    if not messages:
        return "end"
    last = messages[-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "end"


CONDITIONS: Dict[str, Callable[[HamburgerState], str]] = {
    "tools": tools_condition,
}


def register_condition(name: str, fn: Callable[[HamburgerState], str]) -> None:
    CONDITIONS[name] = fn
