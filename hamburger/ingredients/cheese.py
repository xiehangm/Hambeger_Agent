from typing import Any
from langchain_core.messages import SystemMessage
from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class Cheese(HamburgerIngredient):
    """
    芝士片：为主菜增添风味。
    核心功能是注入系统提示词 (System Prompt)。
    """
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt

    def process(self, state: HamburgerState) -> dict[str, Any]:
        # 由于我们希望 SystemMessage 位于消息历史的最上方影响 LLM，
        # 在实际 langgraph 中，直接添加 SystemMessage 到消息树。
        # 如果需要严格放在第一个，可以对整个 messages 进行处理，但 LangChain 大部分模型
        # 本身就识别 SystemMessage。
        
        # 考虑到 langgraph 中 `add_messages` 默认是 append，
        # 如果这是在对话最开始注入的，那么直接以列表形式返回并拼接到消息末尾即可。
        # 这里我们在每次 Cheese 节点被触发时，如果不含 SystemMessage 就添加一条进去。
        messages = state.get("messages", [])
        has_system = any(isinstance(m, SystemMessage) for m in messages)
        
        if not has_system:
            return {"messages": [SystemMessage(content=self.system_prompt)]}
        return {}
