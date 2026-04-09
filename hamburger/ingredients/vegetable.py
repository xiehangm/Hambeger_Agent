from typing import Any, List
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class Vegetable(HamburgerIngredient):
    """
    蔬菜：提供丰富的附加功能。
    核心是执行由肉饼 (LLM) 产生的 Tool Calls，并将执行结果作为 ToolMessage 返还。
    """
    def __init__(self, tools: List[BaseTool]):
        self.tools = tools
        # 使用 langgraph 原生的 ToolNode 来处理标准的 ToolCall 逻辑
        self.tool_node = ToolNode(tools)

    def process(self, state: HamburgerState) -> dict[str, Any]:
        # ToolNode 需要整个 state（主要是 messages 中的最后的 AIMessage 进行判断执行）
        # 它会返回更新后的 dict，包含新的 ToolMessages
        return self.tool_node.invoke(state)
