from typing import Callable, Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient
from hamburger.ingredients.bread import TopBread, BottomBread
from hamburger.ingredients.cheese import Cheese
from hamburger.ingredients.meat import MeatPatty
from hamburger.ingredients.vegetable import Vegetable


def tools_condition(state: HamburgerState) -> Literal["vegetable", "bottom_bread"]:
    """
    判断 LLM 是否返回了 tool_calls，如果有，则走向蔬菜层（执行工具），
    否则走向底层面包（输出结果）。
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
