"""
hamburger.builder —— Recipe → CompiledStateGraph → BurgerAgent

公共入口：
  - compile_agent(recipe, build_ctx, ...) -> BurgerAgent
  - HamburgerBuilder().add_xxx(...).build() -> BurgerAgent

内部辅助：
  - compile_recipe(recipe, build_ctx, ...) -> CompiledStateGraph
    （仍然存在但仅供内部使用，不再从顶层 hamburger 包导出）
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from hamburger.agent import BurgerAgent
from hamburger.factories import CONDITIONS, NODE_FACTORIES
from hamburger.factories import tools_condition as _tools_condition
from hamburger.gateway import AgentCard
from hamburger.ingredients.bread import BottomBread, TopBread
from hamburger.ingredients.cheese import Cheese
from hamburger.ingredients.meat import MeatPatty
from hamburger.ingredients.vegetable import Vegetable
from hamburger.recipes import Recipe, get_recipe
from hamburger.state import HamburgerState


# ============================================================
#  配方 → StateGraph 编译器（内部使用）
# ============================================================
def compile_recipe(
    recipe: Recipe,
    build_ctx: Dict[str, Any],
    *,
    checkpointer: Optional[Any] = None,
    interrupt_before: Optional[List[str]] = None,
):
    """把声明式 Recipe 编译成可执行的 LangGraph CompiledStateGraph。

    内部 API：本函数不再从 ``hamburger`` 顶层导出，所有外部调用应改为
    :func:`compile_agent` 或 :class:`HamburgerBuilder`。
    """
    sg = StateGraph(HamburgerState)

    defaults = recipe.get("default_config", {}) or {}
    merged_ctx = dict(defaults)
    merged_ctx.update({k: v for k, v in build_ctx.items() if v is not None})

    # 1) 节点
    skipped_nodes: set[str] = set()
    for node_spec in recipe.get("nodes", []):
        node_id = node_spec["id"]
        node_type = node_spec["type"]
        factory = NODE_FACTORIES.get(node_type)
        if factory is None:
            raise ValueError(f"未注册的节点类型: {node_type}")
        runnable = factory(node_spec, merged_ctx)
        if runnable is None:
            skipped_nodes.add(node_id)
            continue
        sg.add_node(node_id, runnable)

    # 2) 边（处理被跳过节点的绕行）
    def _resolve_target(target: str) -> str:
        if target == "END" or target not in skipped_nodes:
            return END if target == "END" else target
        for e in recipe.get("edges", []):
            if e.get("source") == target and "target" in e:
                return _resolve_target(e["target"])
        raise ValueError(f"被跳过的节点 {target} 没有非条件出边可绕行")

    for edge in recipe.get("edges", []):
        src = edge["source"]
        src_key = START if src == "START" else src
        if src in skipped_nodes:
            continue
        if "condition" in edge:
            cond_name = edge["condition"]
            cond_fn = CONDITIONS.get(cond_name)
            if cond_fn is None:
                raise ValueError(f"未注册的条件路由: {cond_name}")
            branches = {
                k: _resolve_target(v)
                for k, v in edge.get("branches", {}).items()
            }
            sg.add_conditional_edges(src_key, cond_fn, branches)
        else:
            tgt = edge["target"]
            sg.add_edge(src_key, _resolve_target(tgt))

    # 3) 编译参数
    compile_kwargs: Dict[str, Any] = {}
    caps = recipe.get("capabilities", {}) or {}
    needs_checkpointer = bool(caps.get("memory") or caps.get("hitl"))
    if needs_checkpointer and checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    eff_interrupt_before = (
        interrupt_before
        if interrupt_before is not None
        else caps.get("interrupt_before")
    )
    if eff_interrupt_before:
        filtered = [n for n in eff_interrupt_before if n not in skipped_nodes]
        if filtered:
            compile_kwargs["interrupt_before"] = filtered

    return sg.compile(**compile_kwargs)


# ============================================================
#  Recipe → BurgerAgent（公共入口）
# ============================================================
def compile_agent(
    recipe: Recipe,
    build_ctx: Dict[str, Any],
    *,
    checkpointer: Optional[Any] = None,
    thread_id: Optional[str] = None,
    top_bread: Optional[TopBread] = None,
    bottom_bread: Optional[BottomBread] = None,
    interrupt_before: Optional[List[str]] = None,
    # 能力卡参数（PR-A）：不传时从 recipe + build_ctx 推导
    card_node_id: str = "agent",
    card_name: Optional[str] = None,
    card_description: Optional[str] = None,
    card_tags: Optional[List[str]] = None,
) -> BurgerAgent:
    """端到端构建：recipe → 编译 graph → 装配网关 → BurgerAgent。

    参数：
      recipe          : 配方蓝图
      build_ctx       : 运行时上下文（llm / tools / cheese_prompt / ...）
      checkpointer    : 可选 LangGraph Checkpointer
      thread_id       : 可选指定会话 id；缺省自动生成
      top_bread       : 可选自定义入站网关；缺省 TopBread()
      bottom_bread    : 可选自定义出站网关；缺省 BottomBread()
      interrupt_before: 可选覆盖配方默认的 interrupt_before 列表
      card_node_id    : 能力卡节点 id（套餐中必须唯一，单 Agent 默认 "agent"）
      card_name       : 能力卡名称，缺省取 recipe.label / recipe.name
      card_description: 能力卡描述，缺省取 recipe.description
      card_tags       : 可选标签列表
    """
    top = top_bread or TopBread()
    bot = bottom_bread or BottomBread()

    # I-4：先生成 AgentCard，再入 ctx——让 _factory_cheese 可读到
    tools = build_ctx.get("tools") or []
    tool_names = [getattr(t, "name", str(t)) for t in tools]
    caps = dict((recipe or {}).get("capabilities", {}) or {})
    card = AgentCard(
        node_id=card_node_id,
        name=card_name or (recipe or {}).get(
            "label", (recipe or {}).get("name", "agent")),
        description=card_description or (recipe or {}).get("description", ""),
        recipe_name=(recipe or {}).get("name", ""),
        capabilities=caps,
        tool_names=tool_names,
        tags=list(card_tags or []),
    )

    # 把网关实例 + card 注入 build_ctx，让节点工厂复用
    ctx = {**build_ctx, "_top_bread": top, "_bottom_bread": bot, "card": card}
    graph = compile_recipe(
        recipe, ctx,
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )

    return BurgerAgent(
        graph=graph,
        recipe=recipe,
        top_bread=top,
        bottom_bread=bot,
        thread_id=thread_id or f"thr_{uuid.uuid4().hex[:12]}",
        card=card,
    )


# ============================================================
#  简易脚本式 Builder
# ============================================================
class HamburgerBuilder:
    """像搭积木一样把各个食材组合成一个 Agent。

    本类只负责把食材摆好，最终通过 :meth:`build` 返回 :class:`BurgerAgent`；
    内部直接构图编译，不走 recipe 路径，但同样产出 BurgerAgent。
    """

    def __init__(self) -> None:
        self._top_bread: Optional[TopBread] = None
        self._bottom_bread: Optional[BottomBread] = None
        self._cheese: Optional[Cheese] = None
        self._meat_patty: Optional[MeatPatty] = None
        self._vegetable: Optional[Vegetable] = None

    def add_top_bread(self, bread: TopBread) -> "HamburgerBuilder":
        self._top_bread = bread
        return self

    def add_bottom_bread(self, bread: BottomBread) -> "HamburgerBuilder":
        self._bottom_bread = bread
        return self

    def add_cheese(self, cheese: Cheese) -> "HamburgerBuilder":
        self._cheese = cheese
        return self

    def add_meat_patty(self, meat: MeatPatty) -> "HamburgerBuilder":
        self._meat_patty = meat
        return self

    def add_vegetable(self, veg: Vegetable) -> "HamburgerBuilder":
        self._vegetable = veg
        return self

    def build(
        self,
        *,
        checkpointer: Optional[Any] = None,
        thread_id: Optional[str] = None,
    ) -> BurgerAgent:
        """根据已添加的食材构图、编译并返回 :class:`BurgerAgent`。"""
        if not self._meat_patty:
            raise ValueError("一个汉堡不能没有肉饼 (MeatPatty)！")
        if not self._top_bread or not self._bottom_bread:
            raise ValueError("一个汉堡不能没有顶层和底层面包！")

        sg = StateGraph(HamburgerState)
        sg.add_node("top_bread", self._top_bread)
        sg.add_node("bottom_bread", self._bottom_bread)
        sg.add_node("meat_patty", self._meat_patty)
        if self._cheese:
            sg.add_node("cheese", self._cheese)
        if self._vegetable:
            sg.add_node("vegetable", self._vegetable)

        if self._cheese:
            sg.add_edge(START, "cheese")
            sg.add_edge("cheese", "top_bread")
        else:
            sg.add_edge(START, "top_bread")
        sg.add_edge("top_bread", "meat_patty")

        if self._vegetable:
            sg.add_conditional_edges(
                "meat_patty",
                _tools_condition,
                {"tools": "vegetable", "end": "bottom_bread"},
            )
            sg.add_edge("vegetable", "meat_patty")
        else:
            sg.add_edge("meat_patty", "bottom_bread")
        sg.add_edge("bottom_bread", END)

        graph = sg.compile(
            **({"checkpointer": checkpointer} if checkpointer else {}))

        # 轻量 recipe：让 BurgerAgent 知道 capabilities（比如是否启用 checkpointer）
        recipe: Recipe = get_recipe("tool_agent" if self._vegetable else "basic_chat") \
            or {"name": "custom", "label": "Custom", "capabilities": {}}

        # 能力卡：从 meat_patty 推导工具名
        tool_names: List[str] = []
        meat_tools = getattr(self._meat_patty, "tools", None) or []
        for t in meat_tools:
            tool_names.append(getattr(t, "name", str(t)))
        card = AgentCard(
            node_id="agent",
            name=recipe.get("label", recipe.get("name", "agent")),
            description=recipe.get("description", ""),
            recipe_name=recipe.get("name", ""),
            capabilities=dict(recipe.get("capabilities", {}) or {}),
            tool_names=tool_names,
        )

        return BurgerAgent(
            graph=graph,
            recipe=recipe,
            top_bread=self._top_bread,
            bottom_bread=self._bottom_bread,
            thread_id=thread_id or f"thr_{uuid.uuid4().hex[:12]}",
            card=card,
        )
