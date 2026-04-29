"""
hamburger/combo/compiler.py — 套餐编译器（基于 ComboGateway）

职责：
  1. 读 combo_recipe（pattern + config + 若干 burger_id 引用）
  2. 懒构建 BurgerAgent 并注册到 ComboGateway（每个 node_id 对应一卡）
  3. 调用 patterns.py 的 5 种模式构建器拼拓扑
     —— 节点函数由 ``ComboGateway.adapt(node_id, ...)`` 产生
  4. 返回编译好的外层 CompiledStateGraph

子图与外层之间的数据契约由网关（TopBread/BottomBread + ComboGateway）保证：
  - 入：AgentRequest(message=..., parent_ctx=...)
  - 出：AgentEvent(kind="final"/"handoff"/...) → 由 gateway 解析为 ComboState 增量
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Optional

from langgraph.graph import StateGraph

from hamburger.builder import compile_agent
from hamburger.recipes import get_recipe
from hamburger.combo.gateway import ComboGateway
from hamburger.combo.state import ComboState
from hamburger.combo import patterns as _patterns


PATTERN_KINDS = ("chain", "routing", "parallel", "orchestrator",
                 "evaluator", "dynamic_routing", "supervisor", "handoff")


# 类型：给定 burger_id 返回完整 BuildConfig dict（由 server.py 注入，负责落地持久化）
BurgerLoader = Callable[[str], Dict[str, Any]]
# 类型：根据 BuildConfig dict 构建 build_ctx（包含 llm、tools、cheese_prompt）
BuildCtxFactory = Callable[[Dict[str, Any]], Dict[str, Any]]


def compile_combo(
    combo_recipe: Dict[str, Any],
    *,
    loader: BurgerLoader,
    ctx_factory: BuildCtxFactory,
    llm_factory: Optional[Callable[[], Any]] = None,
    checkpointer: Any = None,
    gateway: Optional[ComboGateway] = None,
):
    """把 combo_recipe 编译成一个 CompiledStateGraph(ComboState)。

    参数：
      combo_recipe : 套餐配方（pattern + config）
      loader       : 由 burger_id 读出 BuildConfig 的回调
      ctx_factory  : 由 BuildConfig 构造 build_ctx 的回调
      llm_factory  : routing / orchestrator / evaluator 模式必需的路由 LLM
      checkpointer : 可选 LangGraph Checkpointer
      gateway      : 可选外部传入的 ComboGateway；不传时内部新建
    """
    pattern = combo_recipe.get("pattern")
    if pattern not in PATTERN_KINDS:
        raise ValueError(f"未知的套餐模式: {pattern!r}")

    cfg = combo_recipe.get("config") or {}
    sg = StateGraph(ComboState)

    gw = gateway or ComboGateway()

    def _wrap(node_id: str, burger_id: str, **kw):
        """patterns.py 调用的工厂：懒构建 + 注册 + adapt 成节点函数。"""
        if not gw.has(node_id):
            record = loader(burger_id)
            if record is None:
                raise ValueError(f"汉堡 {burger_id} 不存在或无法加载")
            config: Dict[str, Any] = dict(record.get("config") or record)
            agent_type = config.get("agent_type") or "basic_chat"
            recipe = get_recipe(agent_type) or get_recipe("basic_chat")
            build_ctx = ctx_factory(config)

            agent = compile_agent(
                recipe, build_ctx,
                checkpointer=None,
                thread_id=f"combo_{node_id}_{uuid.uuid4().hex[:8]}",
                card_node_id=node_id,
                card_name=config.get("name") or recipe.get("label"),
                card_description=config.get(
                    "description") or recipe.get("description", ""),
            )
            gw.register(agent)
            extra_meta = {"burger_id": burger_id, "agent_type": agent_type}
        else:
            extra_meta = {"burger_id": burger_id}

        return gw.adapt(node_id, extra_meta=extra_meta, **kw)

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
    elif pattern == "dynamic_routing":
        _patterns.build_dynamic_routing(sg, cfg, _wrap)
    elif pattern == "supervisor":
        _patterns.build_supervisor(sg, cfg, _wrap)
    elif pattern == "handoff":
        _patterns.build_handoff(sg, cfg, _wrap)

    return sg.compile(checkpointer=checkpointer) if checkpointer else sg.compile()
