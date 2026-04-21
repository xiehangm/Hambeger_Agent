from typing import Any, Callable, Dict, List, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient
from hamburger.ingredients.bread import TopBread, BottomBread
from hamburger.ingredients.cheese import Cheese
from hamburger.ingredients.meat import MeatPatty
from hamburger.ingredients.vegetable import Vegetable
from hamburger.factories import NODE_FACTORIES, CONDITIONS
from hamburger.recipes import Recipe


# ============================================================
#  配方 → StateGraph 编译器
# ============================================================
def compile_recipe(
    recipe: Recipe,
    build_ctx: Dict[str, Any],
    *,
    checkpointer: Optional[Any] = None,
    interrupt_before: Optional[List[str]] = None,
):
    """
    把声明式 Recipe 编译成可执行的 LangGraph CompiledStateGraph。

    参数：
        recipe         : 配方蓝图（hamburger.recipes.Recipe）
        build_ctx      : 运行时构建上下文 {llm, tools, cheese_prompt, ...}
        checkpointer   : 可选 LangGraph Checkpointer（如 MemorySaver）
        interrupt_before: 可选覆盖配方自带的 interrupt_before 列表

    返回：CompiledStateGraph
    """
    sg = StateGraph(HamburgerState)

    # 合并默认运行时配置到 build_ctx（不覆盖用户显式传入的值）
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
            # 工厂返回 None 表示条件性跳过（例如没有工具时的 vegetable）
            skipped_nodes.add(node_id)
            continue
        sg.add_node(node_id, runnable)

    # 2) 边（处理被跳过节点的绕行）
    def _resolve_target(target: str) -> str:
        """如果 target 节点被跳过，递归查找它的下游目标。"""
        if target == "END" or target not in skipped_nodes:
            return END if target == "END" else target
        # 跳过节点 → 沿着它的 outgoing edge 继续
        for e in recipe.get("edges", []):
            if e.get("source") == target and "target" in e:
                return _resolve_target(e["target"])
        raise ValueError(f"被跳过的节点 {target} 没有非条件出边可绕行")

    for edge in recipe.get("edges", []):
        src = edge["source"]
        src_key = START if src == "START" else src

        # 跳过源节点被跳过的边（它的上游会被重定向）
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
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    caps = recipe.get("capabilities", {}) or {}
    eff_interrupt_before = (
        interrupt_before
        if interrupt_before is not None
        else caps.get("interrupt_before")
    )
    # 只保留真实存在的节点，避免因节点跳过导致编译报错
    if eff_interrupt_before:
        filtered = [n for n in eff_interrupt_before if n not in skipped_nodes]
        if filtered:
            compile_kwargs["interrupt_before"] = filtered

    return sg.compile(**compile_kwargs)


# ============================================================
#  条件路由（兼容旧签名：供老代码/测试引用）
# ============================================================
def tools_condition(state: HamburgerState) -> Literal["vegetable", "bottom_bread"]:
    """
    兼容保留：返回下一个节点名。新代码请使用 factories.tools_condition。
    """
    messages = state.get("messages", [])
    if not messages:
        return "bottom_bread"
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "vegetable"
    return "bottom_bread"


class HamburgerBuilder:
    """
    汉堡建造师：像搭积木一样把各个食材组合成一个完整的 Agent (LangGraph)。
    """

    def __init__(self):
        self.builder = StateGraph(HamburgerState)

        self._top_bread: TopBread = None
        self._bottom_bread: BottomBread = None
        self._cheese: Cheese = None
        self._meat_patty: MeatPatty = None
        self._vegetable: Vegetable = None

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

    def build(self):
        """
        根据加入的食材，配置图的节点与边，并编译返回可执行的 Agent。
        """
        # 汉堡必须有肉饼和上下两片面包
        if not self._meat_patty:
            raise ValueError("一个汉堡不能没有肉饼 (MeatPatty)！")
        if not self._top_bread or not self._bottom_bread:
            raise ValueError("一个汉堡不能没有顶层和底层面包！")

        # 1. 注册所有的节点
        self.builder.add_node("top_bread", self._top_bread)
        self.builder.add_node("bottom_bread", self._bottom_bread)
        self.builder.add_node("meat_patty", self._meat_patty)

        if self._cheese:
            self.builder.add_node("cheese", self._cheese)
        if self._vegetable:
            self.builder.add_node("vegetable", self._vegetable)

        # 2. 规划执行路径 (Edges)
        # 流水线：从芝士(如果有) -> 顶层面包
        if self._cheese:
            self.builder.add_edge(START, "cheese")
            self.builder.add_edge("cheese", "top_bread")
        else:
            self.builder.add_edge(START, "top_bread")

        # 顶层面包处理完输入，交给肉饼
        self.builder.add_edge("top_bread", "meat_patty")

        # 从肉饼出发的条件路由
        if self._vegetable:
            self.builder.add_conditional_edges(
                "meat_patty",
                tools_condition,
                {"vegetable": "vegetable", "bottom_bread": "bottom_bread"}
            )
            # 蔬菜(工具)执行完后，必须回传给肉饼继续处理
            self.builder.add_edge("vegetable", "meat_patty")
        else:
            # 如果没有蔬菜，直接走向底层面包
            self.builder.add_edge("meat_patty", "bottom_bread")

        # 底层面包完成，导向 END
        self.builder.add_edge("bottom_bread", END)

        # 编译返回
        return self.builder.compile()
