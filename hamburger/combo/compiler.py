"""
hamburger/combo/compiler.py — 套餐编译器

职责：
  1. 读 combo_recipe（pattern + config + 若干 burger_id 引用）
  2. 对每个引用的汉堡调用 compile_recipe() 拿到子图
  3. 把子图包装成外层 StateGraph(ComboState) 的节点（_wrap_burger_as_node）
  4. 按 pattern 选用 patterns.py 里的构建函数拼拓扑
  5. 返回编译好的外层 CompiledStateGraph

子图输入约定：{"input_text": <str>, "messages": []}
子图输出约定：state["output_text"] 或 最后一条 messages[-1].content 作为该汉堡的回复
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph

from hamburger.builder import compile_recipe
from hamburger.recipes import get_recipe
from hamburger.combo.state import ComboState
from hamburger.combo import patterns as _patterns


PATTERN_KINDS = ("chain", "routing", "parallel", "orchestrator", "evaluator")


# 类型：给定 burger_id 返回完整 BuildConfig dict（由 server.py 注入，负责落地持久化）
BurgerLoader = Callable[[str], Dict[str, Any]]
# 类型：根据 BuildConfig dict 构建 build_ctx（包含 llm、tools、cheese_prompt）
BuildCtxFactory = Callable[[Dict[str, Any]], Dict[str, Any]]


def _extract_reply(state: Dict[str, Any]) -> str:
    """从子图最终 state 中提取文本回复。"""
    if not isinstance(state, dict):
        return ""
    txt = state.get("output_text")
    if txt:
        return str(txt)
    msgs = state.get("messages") or []
    for m in reversed(msgs):
        c = getattr(m, "content", None)
        if isinstance(c, str) and c.strip() and getattr(m, "type", "") != "tool":
            return c
    return ""


def _wrap_burger_as_node(
    node_id: str,
    burger_id: str,
    loader: BurgerLoader,
    ctx_factory: BuildCtxFactory,
    *,
    input_field: str = "user_input",
    input_template: Optional[str] = None,
):
    """把一个已保存的汉堡编译成子图，并包装成外层节点函数。

    参数：
      node_id: 外层图里这个汉堡的节点 id
      burger_id: 已保存汉堡 id
      loader: (burger_id) -> BuildConfig dict
      ctx_factory: (BuildConfig) -> build_ctx dict (含 llm/tools/cheese_prompt)
      input_field: 从 ComboState 哪个字段取输入（默认 user_input）
      input_template: 可选输入模板，支持 Python str.format_map(state)，优先于 input_field

    子图在每次调用时现场编译；因为编译成本不高（纯 Python StateGraph 构造），
    同时避免子图状态跨调用被污染。
    """
    record = loader(burger_id)
    if record is None:
        raise ValueError(f"汉堡 {burger_id} 不存在或无法加载")
    config: Dict[str, Any] = dict(record.get("config") or record)

    agent_type = config.get("agent_type") or "basic_chat"
    recipe = get_recipe(agent_type)
    if recipe is None:
        # 兜底：basic_chat
        recipe = get_recipe("basic_chat")

    interrupt_before = (recipe or {}).get(
        "default_config", {}).get("interrupt_before", []) or []
    caps = (recipe or {}).get("capabilities", {}) or {}
    if caps.get("interrupt_before"):
        interrupt_before = caps["interrupt_before"]

    # 懒编译：首次调用时构建子图，后续复用
    compiled = {"graph": None}

    async def _node(state: ComboState) -> Dict[str, Any]:
        if compiled["graph"] is None:
            build_ctx = ctx_factory(config)
            compiled["graph"] = compile_recipe(
                recipe,
                build_ctx,
                # 子图独立内存；外层状态由外层图负责持久化
                checkpointer=None,
                interrupt_before=list(
                    interrupt_before) if interrupt_before else None,
            )
        graph = compiled["graph"]

        # 组装子图输入
        if input_template:
            try:
                text = input_template.format_map(
                    {k: (v if v is not None else "") for k, v in state.items()})
            except Exception:
                text = str(state.get(input_field) or "")
        else:
            text = str(state.get(input_field) or "")

        sub_input = {
            "input_text": text,
            "messages": [HumanMessage(content=text)] if text else [],
        }
        sub_state = await graph.ainvoke(sub_input)
        reply = _extract_reply(sub_state)

        return {
            "burger_outputs": {node_id: reply},
            "burger_meta": {
                node_id: {
                    "burger_id": burger_id,
                    "agent_type": agent_type,
                    "messages_len": len(sub_state.get("messages") or []) if isinstance(sub_state, dict) else 0,
                }
            },
            "combo_trace": [{
                "kind": "burger",
                "node_id": node_id,
                "burger_id": burger_id,
                "output": reply[:500] if reply else "",
            }],
        }

    _node.__name__ = f"burger_{node_id}"
    return _node


def compile_combo(
    combo_recipe: Dict[str, Any],
    *,
    loader: BurgerLoader,
    ctx_factory: BuildCtxFactory,
    llm_factory: Optional[Callable[[], Any]] = None,
    checkpointer: Any = None,
):
    """把 combo_recipe 编译成一个 CompiledStateGraph(ComboState)。

    combo_recipe 结构（示例见 patterns.py 各 build_* 头注释）：
      {
        "pattern": "chain|routing|parallel|orchestrator|evaluator",
        "config": { ... 模式专属配置 ... }
      }
    """
    pattern = combo_recipe.get("pattern")
    if pattern not in PATTERN_KINDS:
        raise ValueError(f"未知的套餐模式: {pattern!r}")

    cfg = combo_recipe.get("config") or {}
    sg = StateGraph(ComboState)

    def _wrap(node_id: str, burger_id: str, **kw):
        return _wrap_burger_as_node(node_id, burger_id, loader, ctx_factory, **kw)

    if pattern == "chain":
        _patterns.build_chain(sg, cfg, _wrap)
    elif pattern == "routing":
        if llm_factory is None:
            raise ValueError("routing 模式需要传入 llm_factory")
        _patterns.build_routing(sg, cfg, _wrap, llm_factory)
    elif pattern == "parallel":
        _patterns.build_parallel(sg, cfg, _wrap)
    elif pattern == "orchestrator":
        if llm_factory is None:
            raise ValueError("orchestrator 模式需要传入 llm_factory")
        _patterns.build_orchestrator(sg, cfg, _wrap, llm_factory)
    elif pattern == "evaluator":
        if llm_factory is None:
            raise ValueError("evaluator 模式需要传入 llm_factory")
        _patterns.build_evaluator(sg, cfg, _wrap, llm_factory)

    return sg.compile(checkpointer=checkpointer) if checkpointer else sg.compile()
