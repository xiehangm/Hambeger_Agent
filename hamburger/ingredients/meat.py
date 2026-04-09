from typing import Any, List
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class MeatPatty(HamburgerIngredient):
    """
    肉饼：汉堡的核心，代表大语言模型 (LLM) 的调用。
    负责根据历史消息进行思考，输出回复或产生工具调用 (Tool Call)。
    """
    def __init__(self, llm: BaseChatModel, tools: List[BaseTool] = None):
        self.llm = llm
        self.tools = tools or []
        
        # 将工具绑定到大语言模型
        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.llm_with_tools = self.llm

    def process(self, state: HamburgerState) -> dict[str, Any]:
        messages = state.get("messages", [])
        
        # 调用大模型生成回复
        response = self.llm_with_tools.invoke(messages)
        
        # 将生成的 AIMessage (可能携带 tool_calls) 加入到消息池中
        return {"messages": [response]}
